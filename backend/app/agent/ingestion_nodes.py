from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.agent.ingestion_agent import (
    IngestionPlan,
    IngestionProbe,
    plan_from_probe,
    probe_document,
)
from app.agent.ingestion_state import (
    build_ingestion_state_snapshot,
    build_node_contract,
)
from app.core.config import Settings, get_settings
from app.core.logger import get_logger
from app.models.document import Document
from app.rag.chunkers.rule_chunker import RuleChunker
from app.rag.chunk_quality import annotate_chunk_quality
from app.rag.embeddings import BgeEmbeddingModel
from app.rag.loaders.factory import get_loader
from app.rag.normalizers.llm_normalizer import (
    merge_llm_normalized_chunks,
    normalize_chunks_with_llm,
    select_llm_normalization_candidates,
)
from app.rag.preprocessor import DocumentPreprocessor
from app.rag.schemas import DocumentChunk, LoadedDocumentPart
from app.rag.vector_store import ChromaVectorStore

logger = get_logger(__name__)

NODE_LABELS = {
    "FileProbe": "文件探测",
    "StrategyPlanner": "策略规划",
    "RouteTextFirst": "文本优先路由",
    "RouteOcrFirst": "OCR 优先路由",
    "RouteLlmNormalize": "LLM 整理路由",
    "RouteSkipLlmNormalize": "跳过 LLM 整理路由",
    "Parse/OCR": "解析 / OCR",
    "Normalize": "归一化整理",
    "ChunkQuality": "切块质量评估",
    "Index": "向量化入库",
    "Report": "处理报告",
}


@dataclass(slots=True)
class IngestionCallbacks:
    set_status: Callable[[str, str], None]
    update_progress: Callable[[int, int, str], None]
    update_trace: Callable[[dict[str, Any]], None]
    store_plan: Callable[[IngestionPlan], None]
    should_normalize_chunks: Callable[[IngestionPlan | None], bool]
    attach_metadata: Callable[[list[DocumentChunk]], list[DocumentChunk]]
    parser_status_message: Callable[[str], str]


@dataclass(slots=True)
class NodeOutcome:
    state: str = "done"
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IngestionContext:
    db: Session
    document: Document
    callbacks: IngestionCallbacks
    settings: Settings = field(default_factory=get_settings)
    probe: IngestionProbe | None = None
    plan: IngestionPlan | None = None
    parts: list[LoadedDocumentPart] = field(default_factory=list)
    chunks: list[DocumentChunk] = field(default_factory=list)
    indexed_chunks: list[DocumentChunk] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    node_results: dict[str, dict[str, Any]] = field(default_factory=dict)


class IngestionNode(Protocol):
    name: str

    def run(self, context: IngestionContext) -> NodeOutcome | None:
        ...


class FileProbeNode:
    name = "FileProbe"

    def run(self, context: IngestionContext) -> None:
        context.callbacks.set_status(
            "file_probe",
            "文件探测：正在检查文件类型、文本可读性、表格密度和 OCR 需求",
        )
        context.probe = probe_document(
            Path(context.document.storage_path),
            context.document.file_type,
        )
        context.report["probe"] = {
            "file_type": context.probe.file_type,
            "file_size": context.probe.file_size,
            "page_count": context.probe.page_count,
            "text_chars": context.probe.text_chars,
            "table_count": context.probe.table_count,
            "readable": context.probe.readable,
            "probe_error": context.probe.probe_error,
        }
        return NodeOutcome(details=context.report["probe"])


class StrategyPlannerNode:
    name = "StrategyPlanner"

    def run(self, context: IngestionContext) -> None:
        if not context.settings.INGESTION_AGENT_ENABLED:
            context.callbacks.set_status(
                "strategy_planner",
                "策略规划：入库 Agent 未启用，使用默认解析流程",
            )
            context.report["plan"] = {
                "enabled": False,
                "source": "default",
                "reason": "INGESTION_AGENT_ENABLED=false",
            }
            return NodeOutcome(
                state="skipped",
                message="入库 Agent 未启用，使用默认解析流程",
                details=context.report["plan"],
            )

        context.callbacks.set_status(
            "strategy_planner",
            "策略规划：正在选择解析器、OCR 和 LLM 整理策略",
        )
        if context.probe is None:
            context.probe = probe_document(
                Path(context.document.storage_path),
                context.document.file_type,
            )
        context.plan = plan_from_probe(context.probe)
        context.callbacks.store_plan(context.plan)
        context.callbacks.set_status("strategy_planner", context.plan.status_message)
        context.report["plan"] = {
            "primary_reader": context.plan.primary_reader,
            "use_ocr": context.plan.use_ocr,
            "use_llm_preprocessing": context.plan.use_llm_preprocessing,
            "source": context.plan.source,
            "reason": context.plan.reason,
        }
        return NodeOutcome(details=context.report["plan"])


class ParseOcrNode:
    name = "Parse/OCR"

    def run(self, context: IngestionContext) -> None:
        plan = context.plan
        parts: list[LoadedDocumentPart] = []
        force_ocr_after_parse_failure = False
        if not plan or plan.primary_reader != "paddleocr":
            context.callbacks.set_status(
                "parse_ocr",
                context.callbacks.parser_status_message(context.document.file_type),
            )
            loader = get_loader(context.document.file_type)
            try:
                parts = loader.load(context.document.storage_path)
            except Exception as exc:
                if (
                    context.document.file_type == "pdf"
                    and context.settings.PREPROCESS_OCR_FALLBACK_ENABLED
                ):
                    context.callbacks.set_status(
                        "ocr",
                        "文本解析失败，正在回退到 PaddleOCR 识别 PDF",
                    )
                    context.report["parse_fallback"] = {
                        "from": "text_parser",
                        "to": "paddleocr",
                        "reason": str(exc)[:500],
                    }
                    force_ocr_after_parse_failure = True
                    parts = []
                else:
                    context.callbacks.set_status(
                        "failed",
                        "解析 / OCR：当前解析器无法读取文件",
                    )
                    raise ValueError(
                        "File cannot be parsed. It may be encrypted, damaged, "
                        "or missing parser dependencies."
                    ) from exc

        if (
            plan is not None
            and plan.primary_reader == "paddleocr"
            and not context.settings.PREPROCESS_OCR_FALLBACK_ENABLED
        ):
            context.callbacks.set_status(
                "failed",
                "解析 / OCR：策略要求 OCR，但 PREPROCESS_OCR_FALLBACK_ENABLED 未开启",
            )
            raise ValueError("OCR fallback is required by the plan but disabled")

        try:
            context.parts = DocumentPreprocessor().preprocess(
                file_type=context.document.file_type,
                path=context.document.storage_path,
                parts=parts,
                stage_callback=context.callbacks.set_status,
                force_ocr=bool(plan and plan.use_ocr) or force_ocr_after_parse_failure,
                use_llm_preprocessing=(
                    plan.use_llm_preprocessing if plan is not None else None
                ),
            )
        except Exception as exc:
            if (
                context.document.file_type == "pdf"
                and context.settings.PREPROCESS_OCR_FALLBACK_ENABLED
                and parts
                and not (plan and plan.use_ocr)
            ):
                context.callbacks.set_status(
                    "ocr",
                    "预处理发现文本不可用，正在回退到 PaddleOCR 重新识别",
                )
                context.report["parse_fallback"] = {
                    "from": "text_preprocessor",
                    "to": "paddleocr",
                    "reason": str(exc)[:500],
                }
                context.parts = DocumentPreprocessor().preprocess(
                    file_type=context.document.file_type,
                    path=context.document.storage_path,
                    parts=[],
                    stage_callback=context.callbacks.set_status,
                    force_ocr=True,
                    use_llm_preprocessing=(
                        plan.use_llm_preprocessing if plan is not None else None
                    ),
                )
            else:
                raise
        if not context.parts:
            raise ValueError("No text content extracted from document")
        details = {"parsed_part_count": len(context.parts)}
        if "parse_fallback" in context.report:
            details["parse_fallback"] = context.report["parse_fallback"]
        context.report["parsed_part_count"] = len(context.parts)
        return NodeOutcome(details=details)


class NormalizeNode:
    name = "Normalize"

    def run(self, context: IngestionContext) -> None:
        context.callbacks.set_status(
            "normalize",
            "归一化整理：正在切分解析结果并准备低质量 / 表格型切块",
        )
        chunker = RuleChunker(
            chunk_size=context.settings.CHUNK_SIZE,
            chunk_overlap=context.settings.CHUNK_OVERLAP,
        )
        chunks = chunker.split_documents(context.parts)
        if not chunks:
            raise ValueError("No chunks generated from document")

        chunks = annotate_chunk_quality(chunks)
        selection = select_llm_normalization_candidates(chunks)
        should_normalize = context.callbacks.should_normalize_chunks(context.plan)
        normalization_report = {
            "enabled": should_normalize,
            "eligible_count": selection.eligible_count,
            "candidate_count": len(selection.candidates),
            "skipped_existing_count": selection.skipped_existing_count,
            "limit": selection.limit,
            "generated_count": 0,
            "merge_mode": context.settings.CHUNK_LLM_MERGE_MODE,
        }
        if should_normalize and selection.candidates:
            context.callbacks.set_status(
                "normalize",
                "归一化整理：正在对低质量 OCR / 表格型切块进行 LLM 结构化整理",
            )
            normalized_chunks = normalize_chunks_with_llm(
                chunks,
                progress_callback=context.callbacks.update_progress,
            )
            normalization_report["generated_count"] = len(normalized_chunks)
            if normalized_chunks:
                chunks = merge_llm_normalized_chunks(chunks, normalized_chunks)
        elif should_normalize:
            normalization_report["skip_reason"] = "没有需要 LLM 整理的候选切块"
        else:
            normalization_report["skip_reason"] = "当前文档或系统配置未启用 LLM 切块整理"

        context.chunks = chunks
        context.report["normalized_chunk_count"] = len(context.chunks)
        context.report["normalization"] = normalization_report
        return NodeOutcome(
            details={
                "normalized_chunk_count": len(context.chunks),
                **normalization_report,
            }
        )


class ChunkQualityNode:
    name = "ChunkQuality"

    def run(self, context: IngestionContext) -> None:
        context.callbacks.set_status(
            "chunk_quality",
            "切块质量评估：正在评分可读性、OCR 噪声和表格结构",
        )
        context.chunks = annotate_chunk_quality(context.chunks)
        low_quality = 0
        table_chunks = 0
        ocr_chunks = 0
        for chunk in context.chunks:
            metadata = chunk.metadata
            score = metadata.get("chunk_quality_score")
            try:
                if score is not None and float(score) < 0.65:
                    low_quality += 1
            except (TypeError, ValueError):
                pass
            chunk_type = str(metadata.get("chunk_type") or "")
            extraction_method = str(metadata.get("extraction_method") or "")
            if "table" in chunk_type or metadata.get("table_index") is not None:
                table_chunks += 1
            if "ocr" in chunk_type or "ocr" in extraction_method:
                ocr_chunks += 1
        context.report["quality"] = {
            "total_chunks": len(context.chunks),
            "low_quality_chunks": low_quality,
            "table_chunks": table_chunks,
            "ocr_chunks": ocr_chunks,
        }
        return NodeOutcome(details=context.report["quality"])


class IndexNode:
    name = "Index"

    def run(self, context: IngestionContext) -> None:
        context.callbacks.set_status(
            "index",
            "向量化入库：正在附加来源 metadata 并准备写入向量库",
        )
        context.indexed_chunks = context.callbacks.attach_metadata(context.chunks)

        context.callbacks.set_status(
            "embedding",
            "向量化入库：正在调用 BGE Embedding 生成切块向量",
        )
        context.embeddings = BgeEmbeddingModel().embed_texts(
            [chunk.text for chunk in context.indexed_chunks]
        )
        if len(context.embeddings) != len(context.indexed_chunks):
            raise ValueError(
                "Embedding count mismatch: "
                f"chunks={len(context.indexed_chunks)} embeddings={len(context.embeddings)}"
            )

        context.callbacks.set_status(
            "indexing",
            "向量化入库：正在将切块、向量和 metadata 写入 ChromaDB",
        )
        vector_store = ChromaVectorStore()
        vector_store.delete_document(context.document.id)
        chunk_ids = [
            f"doc:{context.document.id}:chunk:{index}"
            for index in range(len(context.indexed_chunks))
        ]
        vector_store.add_documents(chunk_ids, context.indexed_chunks, context.embeddings)
        context.report["indexed_chunk_count"] = len(context.indexed_chunks)
        return NodeOutcome(
            details={
                "indexed_chunk_count": len(context.indexed_chunks),
                "embedding_count": len(context.embeddings),
            }
        )


class ReportNode:
    name = "Report"

    def run(self, context: IngestionContext) -> None:
        context.callbacks.set_status(
            "report",
            "处理报告：正在汇总节点结果并更新最终入库状态",
        )
        context.document.chunk_count = len(context.indexed_chunks)
        context.document.error_message = None
        context.report["document_id"] = context.document.id
        context.report["filename"] = context.document.filename
        logger.info("Ingestion report: %s", context.report)
        context.callbacks.set_status(
            "indexed",
            "入库完成，可以进行检索问答",
        )
        return NodeOutcome(
            details={
                "document_id": context.document.id,
                "filename": context.document.filename,
                "chunk_count": context.document.chunk_count,
            }
        )


class IngestionPipeline:
    def __init__(self, nodes: list[IngestionNode] | None = None) -> None:
        self.nodes = nodes or default_ingestion_nodes()

    def run(self, context: IngestionContext) -> IngestionContext:
        for node in self.nodes:
            run_ingestion_node(node, context)
        return context


def default_ingestion_nodes() -> list[IngestionNode]:
    return [
        FileProbeNode(),
        StrategyPlannerNode(),
        ParseOcrNode(),
        NormalizeNode(),
        ChunkQualityNode(),
        IndexNode(),
        ReportNode(),
    ]


def run_ingestion_node(node: IngestionNode, context: IngestionContext) -> NodeOutcome:
    label = NODE_LABELS.get(node.name, node.name)
    contract = build_node_contract(node.name)
    started_at = _utc_now()
    started_perf = perf_counter()
    context.callbacks.update_trace(
        {
            "node": node.name,
            "label": label,
            "state": "running",
            "started_at": started_at,
            "message": f"{label}开始执行",
            "contract": contract,
            "state_snapshot": build_ingestion_state_snapshot(
                context,
                current_node=node.name,
            ),
        }
    )
    logger.info(
        "Running ingestion node=%s document_id=%s filename=%s",
        node.name,
        context.document.id,
        context.document.filename,
    )
    try:
        outcome = node.run(context) or NodeOutcome()
    except Exception as exc:
        summary = _node_summary(context, node.name)
        duration_ms = _duration_ms(started_perf)
        context.node_results[node.name] = {
            "state": "failed",
            "message": str(exc)[:500],
            "summary": summary,
            "duration_ms": duration_ms,
        }
        context.report["node_results"] = context.node_results
        context.callbacks.update_trace(
            {
                "node": node.name,
                "label": label,
                "state": "failed",
                "started_at": started_at,
                "finished_at": _utc_now(),
                "duration_ms": duration_ms,
                "message": f"{label}失败",
                "error": str(exc)[:500],
                "summary": summary,
                "contract": contract,
                "state_snapshot": build_ingestion_state_snapshot(
                    context,
                    current_node=node.name,
                ),
            }
        )
        raise

    summary = _node_summary(context, node.name)
    if outcome.details:
        summary = {**summary, **outcome.details}
    state = outcome.state or "done"
    duration_ms = _duration_ms(started_perf)
    context.node_results[node.name] = {
        "state": state,
        "message": outcome.message or f"{label}完成",
        "summary": summary,
        "duration_ms": duration_ms,
    }
    context.report["node_results"] = context.node_results
    context.report["state_snapshot"] = build_ingestion_state_snapshot(
        context,
        current_node=node.name,
    )
    context.callbacks.update_trace(
        {
            "node": node.name,
            "label": label,
            "state": state,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "duration_ms": duration_ms,
            "message": outcome.message or f"{label}完成",
            "summary": summary,
            "contract": contract,
            "state_snapshot": context.report["state_snapshot"],
        }
    )
    return outcome


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(started_perf: float) -> int:
    return max(0, int((perf_counter() - started_perf) * 1000))


def _node_summary(context: IngestionContext, node_name: str) -> dict[str, Any]:
    if node_name == "FileProbe" and context.probe:
        return {
            "文件类型": context.probe.file_type,
            "页数": context.probe.page_count,
            "采样文本字符数": context.probe.text_chars,
            "表格数": context.probe.table_count,
            "文本可读": context.probe.readable,
        }
    if node_name == "StrategyPlanner" and context.plan:
        return {
            "主解析器": context.plan.primary_reader,
            "启用 OCR": context.plan.use_ocr,
            "启用 LLM 整理": context.plan.use_llm_preprocessing,
            "策略来源": context.plan.source,
        }
    if node_name == "Parse/OCR":
        return {"解析片段数": len(context.parts)}
    if node_name == "Normalize":
        return {"整理后切块数": len(context.chunks)}
    if node_name == "ChunkQuality":
        return context.report.get("quality", {})
    if node_name == "Index":
        return {
            "入库切块数": len(context.indexed_chunks),
            "向量数": len(context.embeddings),
        }
    if node_name == "Report":
        return {
            "文档ID": context.document.id,
            "文件名": context.document.filename,
            "最终切块数": context.document.chunk_count,
        }
    return {}
