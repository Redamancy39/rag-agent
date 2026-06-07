import re
from typing import Any

from sqlalchemy.orm import Session
from collections.abc import Callable

from app.agent.evidence_judge import EvidenceDecision, EvidenceJudge
from app.agent.query_agent import QueryPlan
from app.core.config import get_settings
from app.core.logger import get_logger
from app.models.user import User
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.retriever import PermissionAwareRetriever
from app.rag.schemas import SourceLocator
from app.rag.table_utils import infer_table_reference
from app.rag.text_quality import is_text_usable
from app.schemas.chat import (
    AnswerSections,
    ChatResponse,
    Citation,
    CitationValidationRead,
    EvidenceDecisionRead,
    EvidenceRow,
    QueryPlanRead,
    RetrievalTraceStep,
    SourceLocationRead,
)
from app.services import document_service, log_service

logger = get_logger(__name__)

NOT_FOUND_ANSWER = "未找到相关答案。"
INLINE_CITATION_PATTERN = re.compile(r"[\[【](\d+)[\]】]")

SYSTEM_PROMPT = """你是一个严谨的企业知识库 RAG 问答助手，只能根据给定检索证据回答。

规则：
1. 不能使用证据之外的知识补全答案。
2. 如果证据没有直接回答用户问题，必须返回 found=false。
3. 如果证据只是主题相近但无法支撑结论，也必须返回 found=false。
4. 需要给出结构化答案，字段包括分类判断、结论、依据。
5. 检索依据表只输出关键字眼或短摘要，不要复制完整原文切块。
6. 结论和依据中的每项事实必须紧跟证据编号，例如“限量为 0.05 mg/kg[1]”。
7. 证据编号只能使用检索证据中提供的 [1]、[2] 等编号，禁止编造编号。
8. evidence_indices 必须列出答案实际引用的全部证据编号。
9. 如果无法为结论和依据提供有效编号，必须返回 found=false。
10. 只输出 JSON，不要输出 Markdown 或额外解释。

JSON 格式：
{
  "found": true,
  "classification": "证据匹配/部分匹配/未找到",
  "conclusion": "一句话结论[1]",
  "basis": "支撑结论的关键依据[1][2]",
  "evidence_indices": [1],
  "evidence_keywords": [
    {"index": 1, "keywords": "关键字眼或短摘要"}
  ]
}

未找到时：
{
  "found": false,
  "classification": "未找到",
  "conclusion": "未找到相关答案。",
  "basis": "未找到可支撑结论的依据。",
  "evidence_indices": [],
  "evidence_keywords": []
}
"""


class RagService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def answer(
        self,
        db: Session,
        *,
        user: User,
        question: str,
        requested_document_ids: list[int] | None = None,
        top_k: int | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> ChatResponse:
        allowed_document_ids = self._allowed_document_ids(
            db,
            user=user,
            requested_document_ids=requested_document_ids,
        )
        if not allowed_document_ids:
            response = _not_found_response("当前账号没有可检索的已入库文档。")
            response.log_id = self._write_log(db, user=user, question=question, response=response)
            return response

        _emit_progress(
            progress_callback,
            stage="query_normalize",
            message="规范化问题并应用本地同义词",
            progress=10,
            allowed_document_count=len(allowed_document_ids),
        )
        hits, retrieval_trace, query_plan = PermissionAwareRetriever().retrieve_with_plan(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k or self.settings.RAG_TOP_K,
            progress_callback=progress_callback,
        )
        citations = self._filter_usable_citations([_hit_to_citation(hit) for hit in hits])
        _emit_progress(
            progress_callback,
            stage="retrieve",
            message=f"混合检索与精排完成，获得 {len(citations)} 条可用证据",
            progress=45,
            hit_count=len(hits),
            citation_count=len(citations),
        )
        if not citations:
            response = _not_found_response()
            response.retrieval_trace = _parse_retrieval_trace(retrieval_trace)
            response.query_plan = _parse_query_plan(query_plan)
            _emit_progress(
                progress_callback,
                stage="completed",
                message="未检索到可用证据",
                progress=100,
                citation_count=0,
            )
            response.log_id = self._write_log(db, user=user, question=question, response=response)
            return response

        _emit_progress(
            progress_callback,
            stage="evidence_judge",
            message=f"检查 {len(citations)} 条证据是否足以回答问题",
            progress=62,
            citation_count=len(citations),
        )
        evidence_decision = EvidenceJudge().judge(
            question=question,
            citations=citations,
            query_plan=query_plan,
        )
        if not evidence_decision.sufficient:
            response = _not_found_response(evidence_decision.reason)
            response.retrieval_trace = _parse_retrieval_trace(retrieval_trace)
            response.query_plan = _parse_query_plan(query_plan)
            response.evidence_decision = _parse_evidence_decision(evidence_decision)
            response.evidence_rows = _fallback_evidence_rows(citations)
            response.citations = _number_citations(_compact_citations(citations))
            _emit_progress(
                progress_callback,
                stage="completed",
                message="证据不足，按知识库约束返回未找到",
                progress=100,
                citation_count=len(citations),
            )
            response.log_id = self._write_log(db, user=user, question=question, response=response)
            return response

        _emit_progress(
            progress_callback,
            stage="generate",
            message="基于证据生成带编号引用的答案",
            progress=78,
            citation_count=len(citations),
        )
        response = self._generate_answer(question, citations)
        response.retrieval_trace = _parse_retrieval_trace(retrieval_trace)
        response.query_plan = _parse_query_plan(query_plan)
        response.evidence_decision = _parse_evidence_decision(evidence_decision)
        _emit_progress(
            progress_callback,
            stage="citation_validate",
            message=(
                "引用编号与来源校验通过"
                if response.citation_validation.valid
                else "引用校验未通过，已阻止输出无来源结论"
            ),
            progress=94,
            cited_indices=response.citation_validation.cited_indices,
            citation_valid=response.citation_validation.valid,
        )
        _emit_progress(
            progress_callback,
            stage="completed",
            message="问答完成",
            progress=100,
            citation_valid=response.citation_validation.valid,
        )
        response.log_id = self._write_log(db, user=user, question=question, response=response)
        return response

    def _allowed_document_ids(
        self,
        db: Session,
        *,
        user: User,
        requested_document_ids: list[int] | None,
    ) -> list[int]:
        documents = document_service.list_accessible_documents(db, user)
        indexed_ids = {document.id for document in documents if document.status == "indexed"}
        if requested_document_ids:
            return sorted(indexed_ids.intersection(requested_document_ids))
        return sorted(indexed_ids)

    def _generate_answer(self, question: str, citations: list[Citation]) -> ChatResponse:
        context = _build_context(citations, max_chars=self.settings.RAG_CONTEXT_MAX_CHARS)
        strategy_hint = _build_strategy_hint(question, citations)
        if not self.settings.OPENAI_API_KEY:
            numbered_citations = _number_citations(_compact_citations(citations))
            sections = AnswerSections(
                classification="已检索，未生成",
                conclusion="已检索到候选依据，但未配置 OPENAI_API_KEY，无法生成结构化答案。",
                basis="可先展开检索依据表查看命中的关键片段。",
                citation=_format_citation_list(numbered_citations),
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(numbered_citations),
                citations=numbered_citations,
                citation_validation=CitationValidationRead(
                    valid=False,
                    warnings=["未配置大模型，未生成可校验的内嵌引用答案。"],
                ),
                retrieval_only=True,
            )

        try:
            payload = OpenAICompatibleLLM().complete_json(
                SYSTEM_PROMPT,
                f"用户问题：{question}\n\n{strategy_hint}\n\n检索证据：\n{context}",
            )
            return _parse_answer_payload(payload, citations)
        except LLMConfigError as exc:
            logger.warning("LLM config error: %s", exc)
            numbered_citations = _number_citations(_compact_citations(citations))
            sections = AnswerSections(
                classification="已检索，未生成",
                conclusion="已检索到候选依据，但大模型配置不可用，无法生成结构化答案。",
                basis=str(exc),
                citation=_format_citation_list(numbered_citations),
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(numbered_citations),
                citations=numbered_citations,
                citation_validation=CitationValidationRead(
                    valid=False,
                    warnings=["大模型配置不可用，未生成可校验的内嵌引用答案。"],
                ),
                retrieval_only=True,
            )
        except Exception as exc:
            logger.warning("LLM answer generation failed: %s", exc)
            numbered_citations = _number_citations(_compact_citations(citations))
            sections = AnswerSections(
                classification="已检索，生成失败",
                conclusion="已检索到候选依据，但大模型生成失败，未输出最终答案。",
                basis=str(exc),
                citation=_format_citation_list(numbered_citations),
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(numbered_citations),
                citations=numbered_citations,
                citation_validation=CitationValidationRead(
                    valid=False,
                    warnings=["大模型生成失败，未生成可校验的内嵌引用答案。"],
                ),
                retrieval_only=True,
            )

    def _filter_usable_citations(self, citations: list[Citation]) -> list[Citation]:
        usable: list[Citation] = []
        for citation in citations:
            if citation.score is not None and citation.score < self.settings.RAG_MIN_SCORE:
                continue
            if not _is_readable_text(
                citation.text,
                min_readable_chars=self.settings.RAG_MIN_READABLE_CHARS,
                max_garbled_token_ratio=self.settings.RAG_MAX_GARBLED_TOKEN_RATIO,
            ):
                continue
            usable.append(citation)
        return usable

    def _write_log(
        self,
        db: Session,
        *,
        user: User,
        question: str,
        response: ChatResponse,
    ) -> int | None:
        chat_log = log_service.create_chat_log(
            db,
            user=user,
            question=question,
            answer=response.answer,
            citations=response.citations,
        )
        return chat_log.id if chat_log else None


def _hit_to_citation(hit: dict) -> Citation:
    metadata = hit.get("metadata") or {}
    locator = SourceLocator.from_metadata(metadata)
    table_label = _table_label_from_metadata_or_text(metadata, str(hit.get("text") or ""))
    return Citation(
        document_id=int(metadata.get("document_id") or 0),
        filename=str(metadata.get("filename") or ""),
        chunk_id=hit.get("id"),
        page=locator.page,
        slide=locator.slide,
        sheet=locator.sheet,
        cell_range=locator.cell_range,
        section_path=locator.section_path,
        paragraph_index=locator.paragraph_index,
        table_index=locator.table_index,
        block_index=locator.block_index,
        location=SourceLocationRead.from_locator(locator),
        table=table_label,
        chunk_type=str(metadata.get("chunk_type") or "") or None,
        score=hit.get("score"),
        text=str(hit.get("text") or ""),
    )


def _parse_retrieval_trace(trace: list[dict]) -> list[RetrievalTraceStep]:
    steps: list[RetrievalTraceStep] = []
    for item in trace:
        try:
            steps.append(RetrievalTraceStep.model_validate(item))
        except Exception:
            continue
    return steps


def _parse_query_plan(plan: QueryPlan | None) -> QueryPlanRead | None:
    if plan is None:
        return None
    try:
        return QueryPlanRead.model_validate(plan.to_dict())
    except Exception:
        return None


def _parse_evidence_decision(
    decision: EvidenceDecision | None,
) -> EvidenceDecisionRead | None:
    if decision is None:
        return None
    try:
        return EvidenceDecisionRead.model_validate(decision.to_dict())
    except Exception:
        return None


def _build_context(citations: list[Citation], max_chars: int) -> str:
    blocks: list[str] = []
    total = 0
    for index, citation in enumerate(citations, start=1):
        location = _format_citation_location(citation)
        table = f"；表：{citation.table}" if citation.table else ""
        score = f"{citation.score:.3f}" if citation.score is not None else "-"
        block = (
            f"[{index}] 文件：{citation.filename}；来源：{location}；"
            f"类型：{citation.chunk_type or '-'}{table}；分数：{score}\n"
            f"{citation.text}"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def _build_strategy_hint(question: str, citations: list[Citation]) -> str:
    if not _looks_like_cross_document_question(question):
        return ""
    filenames = {citation.filename for citation in citations if citation.filename}
    if len(filenames) < 2:
        return ""
    return (
        "检索策略提示：这是跨文档或跨标准问题。若证据分别来自产品标准和通用标准，"
        "可以综合多个证据作答；不要仅因为答案分散在不同文档中就返回未找到。"
        "如果只能回答部分内容，classification 使用“部分匹配”，并在 basis 中明确哪些部分有证据、哪些部分无证据。"
    )


def _looks_like_cross_document_question(question: str) -> bool:
    markers = ("应符合", "引用", "参照", "同时符合", "有何不同", "分别", "都引用")
    if any(marker in question for marker in markers):
        return True
    return len(re.findall(r"\bGB(?:/T)?\s*\d+(?:\.\d+)?(?:[-—]\d{4})?\b", question, flags=re.I)) >= 2


def _parse_answer_payload(payload: dict[str, Any], citations: list[Citation]) -> ChatResponse:
    if payload.get("found") is not True:
        return _not_found_response()

    conclusion = _normalize_inline_citations(_clean_text(payload.get("conclusion")))
    basis = _normalize_inline_citations(_clean_text(payload.get("basis")))
    if not conclusion or conclusion == NOT_FOUND_ANSWER:
        return _not_found_response()

    requested_indices = _payload_evidence_indices(payload)
    inline_indices = _unique_ints(
        [
            *_extract_inline_citation_indices(conclusion),
            *_extract_inline_citation_indices(basis),
        ]
    )
    selected_indices = inline_indices or requested_indices
    valid_source_indices = [
        index for index in selected_indices if 1 <= index <= len(citations)
    ]
    invalid_source_indices = [
        index for index in selected_indices if index not in valid_source_indices
    ]
    if not valid_source_indices:
        return _citation_validation_failure(
            "答案未提供有效的证据编号。",
            invalid_indices=invalid_source_indices,
        )

    index_mapping = {
        source_index: output_index
        for output_index, source_index in enumerate(valid_source_indices, start=1)
    }
    conclusion = _remap_inline_citations(conclusion, index_mapping)
    basis = _remap_inline_citations(basis, index_mapping)
    selected_citations = _number_citations(
        [
            citations[source_index - 1]
            for source_index in valid_source_indices
        ]
    )
    validation = _validate_inline_citations(
        conclusion=conclusion,
        basis=basis,
        citations=selected_citations,
        invalid_source_indices=invalid_source_indices,
    )
    if not validation.valid:
        return _citation_validation_failure(
            "生成答案的引用编号未通过校验，已阻止输出无来源结论。",
            validation=validation,
        )

    sections = AnswerSections(
        classification=_clean_text(payload.get("classification")) or "证据匹配",
        conclusion=conclusion,
        basis=basis,
        citation=_format_citation_list(selected_citations),
    )
    return ChatResponse(
        answer=_sections_to_answer(sections),
        sections=sections,
        evidence_rows=_evidence_rows_from_selected_payload(
            payload,
            selected_citations,
            valid_source_indices,
        ),
        citations=_compact_citations(selected_citations),
        citation_validation=validation,
        retrieval_only=False,
    )


def _evidence_rows_from_selected_payload(
    payload: dict[str, Any],
    citations: list[Citation],
    source_indices: list[int],
) -> list[EvidenceRow]:
    keyword_by_source_index = _payload_evidence_keywords(payload)
    rows: list[EvidenceRow] = []
    for output_index, (source_index, citation) in enumerate(
        zip(source_indices, citations, strict=True),
        start=1,
    ):
        rows.append(
            _citation_to_evidence_row(
                index=output_index,
                citation=citation,
                keywords=(
                    keyword_by_source_index.get(source_index)
                    or _short_keywords(citation.text)
                ),
            )
        )
    return rows


def _payload_evidence_indices(payload: dict[str, Any]) -> list[int]:
    values = payload.get("evidence_indices")
    if not isinstance(values, list):
        return []
    return _unique_ints(
        [
            index
            for value in values
            if (index := _to_int_or_none(value)) is not None
        ]
    )


def _payload_evidence_keywords(payload: dict[str, Any]) -> dict[int, str]:
    keyword_by_index: dict[int, str] = {}
    raw_keywords = payload.get("evidence_keywords")
    if not isinstance(raw_keywords, list):
        return keyword_by_index
    for item in raw_keywords:
        if not isinstance(item, dict):
            continue
        index = _to_int_or_none(item.get("index"))
        keywords = _clean_text(item.get("keywords"))
        if index and keywords:
            keyword_by_index[index] = keywords
    return keyword_by_index


def _fallback_evidence_rows(citations: list[Citation]) -> list[EvidenceRow]:
    return [
        _citation_to_evidence_row(
            index=citation.citation_id or index,
            citation=citation,
            keywords=_short_keywords(citation.text),
        )
        for index, citation in enumerate(citations, start=1)
    ]


def _compact_citations(citations: list[Citation]) -> list[Citation]:
    return [
        citation.model_copy(update={"text": _short_keywords(citation.text, max_chars=240)})
        for citation in citations
    ]


def _number_citations(citations: list[Citation]) -> list[Citation]:
    return [
        citation.model_copy(update={"citation_id": index})
        for index, citation in enumerate(citations, start=1)
    ]


def _citation_to_evidence_row(index: int, citation: Citation, keywords: str) -> EvidenceRow:
    return EvidenceRow(
        index=index,
        score=citation.score,
        filename=citation.filename,
        page=citation.page,
        slide=citation.slide,
        section_path=citation.section_path,
        sheet=citation.sheet,
        cell_range=citation.cell_range,
        paragraph_index=citation.paragraph_index,
        table_index=citation.table_index,
        block_index=citation.block_index,
        location=citation.location,
        table=citation.table or _table_label_from_text(citation.text),
        chunk_id=citation.chunk_id,
        keywords=keywords,
    )


def _table_label_from_text(text: str) -> str | None:
    label, _ = infer_table_reference(text)
    if label:
        return label
    for marker in ("表号：", "表：", "表 "):
        if marker in text:
            tail = text.split(marker, 1)[1].strip()
            return tail.splitlines()[0][:30] if tail else None
    return None


def _table_label_from_metadata_or_text(metadata: dict, text: str) -> str | None:
    label, _ = infer_table_reference(text, metadata)
    return label


def _short_keywords(text: str, max_chars: int = 120) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:max_chars] + ("..." if len(cleaned) > max_chars else "")


def _format_citation_reference(citation: Citation) -> str:
    location = _format_citation_location(citation)
    location_text = f"，{location}" if location else ""
    table = f"，{citation.table}" if citation.table else ""
    return f"{citation.filename}{location_text}{table}"


def _format_citation_location(citation: Citation) -> str:
    if citation.location is not None:
        return citation.location.label
    return SourceLocator(
        page=citation.page,
        slide=citation.slide,
        sheet=citation.sheet,
        cell_range=citation.cell_range,
        section_path=citation.section_path,
        paragraph_index=citation.paragraph_index,
        table_index=citation.table_index,
        block_index=citation.block_index,
    ).display_label()


def _format_citation_list(citations: list[Citation]) -> str:
    if not citations:
        return "无"
    return "；".join(
        f"[{citation.citation_id or index}] {_format_citation_reference(citation)}"
        for index, citation in enumerate(citations, start=1)
    )


def _normalize_inline_citations(text: str) -> str:
    return re.sub(r"【\s*(\d+)\s*】", r"[\1]", text)


def _extract_inline_citation_indices(text: str) -> list[int]:
    return _unique_ints(
        [int(match.group(1)) for match in INLINE_CITATION_PATTERN.finditer(text)]
    )


def _remap_inline_citations(text: str, index_mapping: dict[int, int]) -> str:
    def replace(match: re.Match[str]) -> str:
        source_index = int(match.group(1))
        output_index = index_mapping.get(source_index)
        return f"[{output_index}]" if output_index is not None else match.group(0)

    return INLINE_CITATION_PATTERN.sub(replace, text)


def _validate_inline_citations(
    *,
    conclusion: str,
    basis: str,
    citations: list[Citation],
    invalid_source_indices: list[int] | None = None,
) -> CitationValidationRead:
    valid_ids = {
        citation.citation_id
        for citation in citations
        if citation.citation_id is not None
    }
    conclusion_indices = _extract_inline_citation_indices(conclusion)
    basis_indices = _extract_inline_citation_indices(basis)
    cited_indices = _unique_ints([*conclusion_indices, *basis_indices])
    invalid_indices = _unique_ints(
        [
            *(invalid_source_indices or []),
            *[index for index in cited_indices if index not in valid_ids],
        ]
    )
    uncited_sections: list[str] = []
    if not conclusion_indices:
        uncited_sections.append("conclusion")
    if not basis_indices:
        uncited_sections.append("basis")
    warnings: list[str] = []
    if invalid_indices:
        warnings.append("答案包含不存在或未授权的引用编号。")
    if uncited_sections:
        warnings.append("结论或依据缺少内嵌引用。")
    return CitationValidationRead(
        valid=bool(cited_indices) and not invalid_indices and not uncited_sections,
        cited_indices=cited_indices,
        invalid_indices=invalid_indices,
        uncited_sections=uncited_sections,
        warnings=warnings,
    )


def _citation_validation_failure(
    reason: str,
    *,
    invalid_indices: list[int] | None = None,
    validation: CitationValidationRead | None = None,
) -> ChatResponse:
    response = _not_found_response(reason)
    response.citation_validation = validation or CitationValidationRead(
        valid=False,
        invalid_indices=invalid_indices or [],
        warnings=[reason],
    )
    return response


def _unique_ints(values: list[int]) -> list[int]:
    unique: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _sections_to_answer(sections: AnswerSections) -> str:
    return "\n".join(
        [
            f"分类判断：{sections.classification}",
            f"结论：{sections.conclusion}",
            f"依据：{sections.basis}",
            f"引用：{sections.citation}",
        ]
    )


def _not_found_response(reason: str | None = None) -> ChatResponse:
    sections = AnswerSections(
        classification="未找到",
        conclusion=NOT_FOUND_ANSWER,
        basis=reason or "未找到可支撑结论的依据。",
        citation="无",
    )
    return ChatResponse(
        answer=_sections_to_answer(sections),
        sections=sections,
        evidence_rows=[],
        citations=[],
        citation_validation=CitationValidationRead(valid=True),
        retrieval_only=True,
    )


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _to_int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_readable_text(
    text: str,
    *,
    min_readable_chars: int,
    max_garbled_token_ratio: float,
) -> bool:
    return is_text_usable(
        text,
        min_readable_chars=min_readable_chars,
        max_garbled_token_ratio=max_garbled_token_ratio,
    )


def _emit_progress(
    callback: Callable[[dict], None] | None,
    **event: object,
) -> None:
    if callback is not None:
        callback(dict(event))
