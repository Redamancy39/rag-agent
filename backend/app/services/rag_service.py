from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logger import get_logger
from app.models.user import User
from app.rag.llm_client import LLMConfigError, OpenAICompatibleLLM
from app.rag.retriever import PermissionAwareRetriever
from app.rag.text_quality import is_text_usable
from app.schemas.chat import AnswerSections, ChatResponse, Citation, EvidenceRow
from app.services import document_service, log_service

logger = get_logger(__name__)

NOT_FOUND_ANSWER = "未找到相关答案。"

SYSTEM_PROMPT = """你是一个严谨的企业知识库 RAG 问答助手，只能根据给定检索证据回答。

规则：
1. 不能使用证据之外的知识补全答案。
2. 如果证据没有直接回答用户问题，必须返回 found=false。
3. 如果证据只是主题相近但无法支撑结论，也必须返回 found=false。
4. 需要给出结构化答案，字段包括分类判断、结论、依据、引用。
5. 检索依据表只输出关键字眼或短摘要，不要复制完整原文切块。
6. 只输出 JSON，不要输出 Markdown 或额外解释。

JSON 格式：
{
  "found": true,
  "classification": "证据匹配/部分匹配/未找到",
  "conclusion": "一句话结论",
  "basis": "支撑结论的关键依据，必须来自证据",
  "citation": "引用来源，例如：GB xxxx，第x页，表x",
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
  "citation": "无",
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

        hits = PermissionAwareRetriever().retrieve(
            question,
            allowed_document_ids=allowed_document_ids,
            top_k=top_k or self.settings.RAG_TOP_K,
        )
        citations = self._filter_usable_citations([_hit_to_citation(hit) for hit in hits])
        if not citations:
            response = _not_found_response()
            response.log_id = self._write_log(db, user=user, question=question, response=response)
            return response

        response = self._generate_answer(question, citations)
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
        if not self.settings.OPENAI_API_KEY:
            sections = AnswerSections(
                classification="已检索，未生成",
                conclusion="已检索到候选依据，但未配置 OPENAI_API_KEY，无法生成结构化答案。",
                basis="可先展开检索依据表查看命中的关键片段。",
                citation=_format_citation_reference(citations[0]) if citations else "无",
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(citations),
                citations=_compact_citations(citations),
                retrieval_only=True,
            )

        try:
            payload = OpenAICompatibleLLM().complete_json(
                SYSTEM_PROMPT,
                f"用户问题：{question}\n\n检索证据：\n{context}",
            )
            return _parse_answer_payload(payload, citations)
        except LLMConfigError as exc:
            logger.warning("LLM config error: %s", exc)
            sections = AnswerSections(
                classification="已检索，未生成",
                conclusion="已检索到候选依据，但大模型配置不可用，无法生成结构化答案。",
                basis=str(exc),
                citation=_format_citation_reference(citations[0]) if citations else "无",
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(citations),
                citations=_compact_citations(citations),
                retrieval_only=True,
            )
        except Exception as exc:
            logger.warning("LLM answer generation failed: %s", exc)
            sections = AnswerSections(
                classification="已检索，生成失败",
                conclusion="已检索到候选依据，但大模型生成失败，未输出最终答案。",
                basis=str(exc),
                citation=_format_citation_reference(citations[0]) if citations else "无",
            )
            return ChatResponse(
                answer=_sections_to_answer(sections),
                sections=sections,
                evidence_rows=_fallback_evidence_rows(citations),
                citations=_compact_citations(citations),
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
    return Citation(
        document_id=int(metadata.get("document_id") or 0),
        filename=str(metadata.get("filename") or ""),
        chunk_id=hit.get("id"),
        page=_to_int_or_none(metadata.get("page")),
        chunk_type=str(metadata.get("chunk_type") or "") or None,
        score=hit.get("score"),
        text=str(hit.get("text") or ""),
    )


def _build_context(citations: list[Citation], max_chars: int) -> str:
    blocks: list[str] = []
    total = 0
    for index, citation in enumerate(citations, start=1):
        page = f"第 {citation.page} 页" if citation.page else "无页码"
        score = f"{citation.score:.3f}" if citation.score is not None else "-"
        block = (
            f"[{index}] 文件：{citation.filename}；来源：{page}；"
            f"类型：{citation.chunk_type or '-'}；分数：{score}\n"
            f"{citation.text}"
        )
        if total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def _parse_answer_payload(payload: dict[str, Any], citations: list[Citation]) -> ChatResponse:
    if payload.get("found") is not True:
        response = _not_found_response()
        response.evidence_rows = _evidence_rows_from_payload(payload, citations)
        response.citations = _compact_citations(citations)
        return response

    sections = AnswerSections(
        classification=_clean_text(payload.get("classification")) or "证据匹配",
        conclusion=_clean_text(payload.get("conclusion")) or NOT_FOUND_ANSWER,
        basis=_clean_text(payload.get("basis")) or "未找到可支撑结论的依据。",
        citation=_clean_text(payload.get("citation")) or "无",
    )
    evidence_indices = payload.get("evidence_indices")
    if (
        not sections.conclusion
        or sections.conclusion == NOT_FOUND_ANSWER
        or not isinstance(evidence_indices, list)
        or not evidence_indices
    ):
        response = _not_found_response()
        response.evidence_rows = _evidence_rows_from_payload(payload, citations)
        response.citations = _compact_citations(citations)
        return response

    return ChatResponse(
        answer=_sections_to_answer(sections),
        sections=sections,
        evidence_rows=_evidence_rows_from_payload(payload, citations),
        citations=_compact_citations(citations),
        retrieval_only=False,
    )


def _evidence_rows_from_payload(
    payload: dict[str, Any],
    citations: list[Citation],
) -> list[EvidenceRow]:
    keyword_by_index: dict[int, str] = {}
    raw_keywords = payload.get("evidence_keywords")
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            if not isinstance(item, dict):
                continue
            index = _to_int_or_none(item.get("index"))
            keywords = _clean_text(item.get("keywords"))
            if index and keywords:
                keyword_by_index[index] = keywords

    evidence_indices = payload.get("evidence_indices")
    if isinstance(evidence_indices, list) and evidence_indices:
        selected = {
            index
            for value in evidence_indices
            if (index := _to_int_or_none(value)) is not None
        }
    else:
        selected = set(range(1, len(citations) + 1))

    rows: list[EvidenceRow] = []
    for index, citation in enumerate(citations, start=1):
        if index not in selected:
            continue
        rows.append(
            _citation_to_evidence_row(
                index=index,
                citation=citation,
                keywords=keyword_by_index.get(index) or _short_keywords(citation.text),
            )
        )
    return rows


def _fallback_evidence_rows(citations: list[Citation]) -> list[EvidenceRow]:
    return [
        _citation_to_evidence_row(
            index=index,
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


def _citation_to_evidence_row(index: int, citation: Citation, keywords: str) -> EvidenceRow:
    return EvidenceRow(
        index=index,
        score=citation.score,
        filename=citation.filename,
        page=citation.page,
        table=_table_label_from_text(citation.text),
        chunk_id=citation.chunk_id,
        keywords=keywords,
    )


def _table_label_from_text(text: str) -> str | None:
    for marker in ("表号：", "表：", "表 "):
        if marker in text:
            tail = text.split(marker, 1)[1].strip()
            return tail.splitlines()[0][:30] if tail else None
    return None


def _short_keywords(text: str, max_chars: int = 120) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:max_chars] + ("..." if len(cleaned) > max_chars else "")


def _format_citation_reference(citation: Citation) -> str:
    page = f"，第 {citation.page} 页" if citation.page else ""
    return f"{citation.filename}{page}"


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
