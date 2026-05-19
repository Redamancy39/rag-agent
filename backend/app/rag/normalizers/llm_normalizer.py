from typing import Any
from collections.abc import Callable

from app.core.config import get_settings
from app.core.logger import get_logger
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.schemas import DocumentChunk, LoadedDocumentPart

logger = get_logger(__name__)


SYSTEM_PROMPT = """你是企业知识库入库预处理器。你的任务是把国标、法规、检测限量类文本整理成可检索事实。
只输出 JSON，不要输出 Markdown 或解释。
要求：
1. 不要编造原文没有的信息。
2. 保留食品类别、项目名称、限量值、单位、适用条件、页码或表格来源。
3. 如果无法确定字段，使用空字符串。
4. 每个 facts 元素应可直接用于向量检索。
JSON 格式：
{
  "facts": [
    {
      "question": "用户可能会怎么问",
      "answer": "简洁答案",
      "subject": "食品类别或适用对象",
      "item": "污染物/农药/指标/项目",
      "limit_value": "限量值",
      "unit": "单位",
      "condition": "适用条件",
      "evidence": "原文证据短句"
    }
  ]
}
"""


CHUNK_NORMALIZATION_PROMPT = """你是严谨的 RAG 入库清洗助手。你的任务是把 OCR 或表格型切块整理成更适合检索的中文事实文本。

要求：
1. 只能使用原始切块中的信息，禁止补充未出现的数值、单位、页码、条款或结论。
2. 可以修复明显的断行、表格行列关系、单位空格和 OCR 中的轻微排版问题。
3. 如果某个数值或列关系无法从原文确定，必须写“待核验”或“无法确定”，不能猜测。
4. 保留文件名、页码、条款号、表号、项目名、限量值、单位、适用条件等可溯源信息。
5. 只返回 JSON，不要返回 Markdown。

JSON 格式：
{
  "should_use": true,
  "normalized_text": "整理后的事实文本",
  "quality_notes": "说明做了哪些整理，以及哪些内容仍需核验",
  "confidence": 0.0
}
"""


class StructuredFactNormalizer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._llm: OpenAICompatibleLLM | None = None

    def normalize(self, part: LoadedDocumentPart) -> list[LoadedDocumentPart]:
        chunk_type = str(part.metadata.get("chunk_type") or "")
        if chunk_type not in self.settings.PREPROCESS_LLM_TARGET_CHUNK_TYPES:
            return []
        if not part.text.strip():
            return []

        llm = self._get_llm()
        payload = llm.complete_json(SYSTEM_PROMPT, self._build_user_prompt(part))
        facts = payload.get("facts")
        if not isinstance(facts, list):
            return []

        normalized_parts: list[LoadedDocumentPart] = []
        for fact_index, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                continue
            text = _fact_to_text(fact)
            if not text:
                continue
            metadata = dict(part.metadata)
            metadata.update(
                {
                    "chunk_type": "llm_structured_fact",
                    "source_chunk_type": chunk_type,
                    "llm_fact_index": fact_index,
                    "extraction_method": "llm_structured_normalization",
                    "llm_model": self.settings.OPENAI_MODEL_NAME,
                }
            )
            normalized_parts.append(LoadedDocumentPart(text=text, metadata=metadata))
        return normalized_parts

    def _get_llm(self) -> OpenAICompatibleLLM:
        if self._llm is None:
            self._llm = OpenAICompatibleLLM()
        return self._llm

    def _build_user_prompt(self, part: LoadedDocumentPart) -> str:
        text = part.text[: self.settings.PREPROCESS_LLM_MAX_INPUT_CHARS]
        page = part.metadata.get("page") or ""
        table_index = part.metadata.get("table_index") or ""
        table_title = part.metadata.get("table_title") or ""
        return (
            f"页码：{page}\n"
            f"表格序号：{table_index}\n"
            f"表题：{table_title}\n"
            "待整理文本：\n"
            f"{text}"
        )


def normalize_with_llm(parts: list[LoadedDocumentPart]) -> list[LoadedDocumentPart]:
    settings = get_settings()
    if not settings.PREPROCESS_LLM_ENABLED:
        return []

    normalizer = StructuredFactNormalizer()
    normalized_parts: list[LoadedDocumentPart] = []
    for part in parts:
        try:
            normalized_parts.extend(normalizer.normalize(part))
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning(
                "LLM preprocessing failed chunk_type=%s page=%s error=%s",
                part.metadata.get("chunk_type"),
                part.metadata.get("page"),
                exc,
            )
    return normalized_parts


class ChunkTextNormalizer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._llm: OpenAICompatibleLLM | None = None

    def normalize(self, chunk: DocumentChunk) -> DocumentChunk | None:
        text = chunk.text.strip()
        if len(text) < self.settings.CHUNK_LLM_MIN_INPUT_CHARS:
            return None
        payload = self._get_llm().complete_json(
            CHUNK_NORMALIZATION_PROMPT,
            self._build_user_prompt(chunk),
        )
        if payload.get("should_use") is False:
            return None
        normalized_text = _clean_value(payload.get("normalized_text"))
        if len(normalized_text) < self.settings.CHUNK_LLM_MIN_INPUT_CHARS:
            return None
        if _same_text(normalized_text, text):
            return None

        metadata = dict(chunk.metadata)
        metadata.update(
            {
                "chunk_type": "llm_normalized_chunk",
                "source_chunk_type": chunk.metadata.get("chunk_type"),
                "source_local_chunk_index": chunk.metadata.get("local_chunk_index"),
                "extraction_method": "llm_chunk_normalization",
                "llm_model": self.settings.OPENAI_MODEL_NAME,
                "llm_normalized": True,
                "llm_confidence": _safe_confidence(payload.get("confidence")),
                "llm_quality_notes": _clean_value(payload.get("quality_notes"))[:500],
                "raw_text_preview": text[:800],
                "needs_llm_normalization": False,
            }
        )
        return DocumentChunk(text=normalized_text, metadata=metadata)

    def _get_llm(self) -> OpenAICompatibleLLM:
        if self._llm is None:
            self._llm = OpenAICompatibleLLM()
        return self._llm

    def _build_user_prompt(self, chunk: DocumentChunk) -> str:
        metadata = chunk.metadata
        text = chunk.text[: self.settings.PREPROCESS_LLM_MAX_INPUT_CHARS]
        return (
            f"文件名: {metadata.get('filename') or metadata.get('source') or ''}\n"
            f"页码: {metadata.get('page') or ''}\n"
            f"内容类型: {metadata.get('chunk_type') or ''}\n"
            f"质量分: {metadata.get('chunk_quality_score') or ''}\n"
            f"质量标记: {metadata.get('chunk_quality_flags') or ''}\n"
            f"OCR平均置信度: {metadata.get('ocr_avg_score') or ''}\n"
            "原始切块:\n"
            f"{text}"
        )


def normalize_chunks_with_llm(
    chunks: list[DocumentChunk],
    progress_callback: Callable[[int, int, str], None] | None = None,
    *,
    force: bool = False,
) -> list[DocumentChunk]:
    settings = get_settings()
    if not (
        (settings.PREPROCESS_LLM_ENABLED or force)
        and settings.CHUNK_LLM_NORMALIZATION_ENABLED
    ):
        return []

    normalizer = ChunkTextNormalizer()
    normalized_chunks: list[DocumentChunk] = []
    candidates = [
        chunk
        for chunk in chunks
        if bool(chunk.metadata.get("needs_llm_normalization"))
    ][: settings.CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT]
    total = len(candidates)
    if progress_callback:
        progress_callback(0, total, f"待整理切块 {total} 个")
    for index, chunk in enumerate(candidates, start=1):
        if progress_callback:
            progress_callback(
                index - 1,
                total,
                f"正在整理 OCR/表格切块：第 {index} / {total} 个（已完成 {index - 1} 个）",
            )
        try:
            normalized = normalizer.normalize(chunk)
        except LLMConfigError as exc:
            logger.warning("Chunk LLM normalization skipped: %s", exc)
            return normalized_chunks
        except Exception as exc:
            logger.warning(
                "Chunk LLM normalization failed page=%s local_chunk=%s error=%s",
                chunk.metadata.get("page"),
                chunk.metadata.get("local_chunk_index"),
                exc,
            )
            continue
        if normalized:
            normalized_chunks.append(normalized)
        if progress_callback:
            progress_callback(
                index,
                total,
                f"已处理 OCR/表格切块：{index} / {total}",
            )
    if progress_callback:
        progress_callback(total, total, f"LLM 切块整理完成：{total} / {total}")
    return normalized_chunks


def _fact_to_text(fact: dict[str, Any]) -> str:
    fields = {
        "可检索问法": fact.get("question"),
        "答案": fact.get("answer"),
        "适用对象": fact.get("subject"),
        "项目": fact.get("item"),
        "限量值": fact.get("limit_value"),
        "单位": fact.get("unit"),
        "适用条件": fact.get("condition"),
        "原文证据": fact.get("evidence"),
    }
    lines = [f"{key}：{_clean_value(value)}" for key, value in fields.items() if _clean_value(value)]
    if not lines:
        return ""
    return "结构化检索事实：\n" + "\n".join(lines)


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _same_text(left: str, right: str) -> bool:
    return "".join(left.split()) == "".join(right.split())
