import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rag.schemas import SourceLocator


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[int] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SourceLocationRead(BaseModel):
    kind: str = "document"
    key: str = "document"
    label: str = "文档级"
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    section_path: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    block_index: int | None = None

    @classmethod
    def from_locator(cls, locator: SourceLocator) -> "SourceLocationRead":
        return cls.model_validate(locator.to_read_dict())


class Citation(BaseModel):
    citation_id: int | None = None
    document_id: int
    filename: str
    chunk_id: str | None = None
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    section_path: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    block_index: int | None = None
    location: SourceLocationRead | None = None
    table: str | None = None
    chunk_type: str | None = None
    score: float | None = None
    text: str

    @model_validator(mode="after")
    def populate_location(self) -> "Citation":
        locator = _locator_from_read_model(self)
        self.location = SourceLocationRead.from_locator(locator)
        return self


class AnswerSections(BaseModel):
    classification: str = "未找到"
    conclusion: str = "未找到相关答案。"
    basis: str = "未找到可支撑结论的依据。"
    citation: str = "无"


class EvidenceRow(BaseModel):
    index: int
    score: float | None = None
    filename: str
    page: int | None = None
    slide: int | None = None
    section_path: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    block_index: int | None = None
    location: SourceLocationRead | None = None
    table: str | None = None
    chunk_id: str | None = None
    keywords: str

    @model_validator(mode="after")
    def populate_location(self) -> "EvidenceRow":
        self.location = SourceLocationRead.from_locator(_locator_from_read_model(self))
        return self


class RetrievalTraceHit(BaseModel):
    rank: int
    score: float | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    bm25_score: float | None = None
    raw_bm25_score: float | None = None
    pre_rerank_score: float | None = None
    rerank_score: float | None = None
    distance: float | None = None
    filename: str
    page: int | None = None
    slide: int | None = None
    section_path: str | None = None
    sheet: str | None = None
    cell_range: str | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    block_index: int | None = None
    location: SourceLocationRead | None = None
    table: str | None = None
    chunk_id: str | None = None
    retrieval_source: str | None = None
    matched_terms: list[str] = Field(default_factory=list)
    preserved_from_pre_rerank: bool = False
    selected_for_answer: bool = False
    citation_id: int | None = None
    text_preview: str = ""

    @model_validator(mode="after")
    def populate_location(self) -> "RetrievalTraceHit":
        self.location = SourceLocationRead.from_locator(_locator_from_read_model(self))
        return self


class RetrievalTraceStep(BaseModel):
    query_index: int
    query: str
    source: str
    hit_count: int
    duration_ms: int | None = None
    top_hits: list[RetrievalTraceHit] = Field(default_factory=list)


class QueryPlanRead(BaseModel):
    original_question: str
    normalized_question: str
    needs_rewrite: bool
    question_type: str
    source: str
    reason: str
    standard_refs: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    sub_questions: list[str] = Field(default_factory=list)
    rewritten_queries: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    synonym_expansions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    llm_used: bool = False
    warnings: list[str] = Field(default_factory=list)


class EvidenceDecisionRead(BaseModel):
    sufficient: bool
    source: str
    reason: str
    confidence: float = 0.0
    missing_requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CitationValidationRead(BaseModel):
    valid: bool = False
    cited_indices: list[int] = Field(default_factory=list)
    invalid_indices: list[int] = Field(default_factory=list)
    uncited_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RetrievalScopeRead(BaseModel):
    requested_document_ids: list[int] = Field(default_factory=list)
    allowed_document_ids: list[int] = Field(default_factory=list)
    top_k: int = 0


class ChatResponse(BaseModel):
    answer: str
    sections: AnswerSections = Field(default_factory=AnswerSections)
    evidence_rows: list[EvidenceRow] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    retrieval_trace: list[RetrievalTraceStep] = Field(default_factory=list)
    query_plan: QueryPlanRead | None = None
    evidence_decision: EvidenceDecisionRead | None = None
    citation_validation: CitationValidationRead = Field(
        default_factory=CitationValidationRead
    )
    retrieval_scope: RetrievalScopeRead = Field(default_factory=RetrievalScopeRead)
    retrieval_only: bool = False
    log_id: int | None = None


class ChatJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: str
    stage: str
    message: str | None = None
    error_message: str | None = None
    question: str
    document_ids_json: list[int] | None = None
    top_k: int
    progress_percent: int = 0
    progress_detail: str | None = None
    trace_json: list[dict[str, Any]] | None = None
    response_json: ChatResponse | None = None
    log_id: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("document_ids_json", mode="before")
    @classmethod
    def parse_document_ids(cls, value: Any) -> list[int] | None:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, list):
                ids: list[int] = []
                for item in parsed:
                    try:
                        ids.append(int(item))
                    except (TypeError, ValueError):
                        continue
                return ids
        return None

    @field_validator("trace_json", mode="before")
    @classmethod
    def parse_trace_json(cls, value: Any) -> list[dict[str, Any]] | None:
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [{"raw": value}]
            if isinstance(parsed, list):
                return [
                    item if isinstance(item, dict) else {"value": item}
                    for item in parsed
                ]
            return [{"value": parsed}]
        return None

    @field_validator("response_json", mode="before")
    @classmethod
    def parse_response_json(cls, value: Any) -> ChatResponse | None:
        if value is None or isinstance(value, ChatResponse):
            return value
        if isinstance(value, dict):
            return ChatResponse.model_validate(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                return ChatResponse.model_validate(parsed)
        return None


class ChatLogRead(BaseModel):
    id: int
    user_id: int
    question: str
    answer: str
    citations_json: str | None
    retrieval_trace: list[RetrievalTraceStep] = Field(default_factory=list)
    query_plan: QueryPlanRead | None = None
    evidence_decision: EvidenceDecisionRead | None = None
    citation_validation: CitationValidationRead = Field(
        default_factory=CitationValidationRead
    )
    retrieval_scope: RetrievalScopeRead = Field(default_factory=RetrievalScopeRead)
    response: ChatResponse | None = None
    created_at: datetime


def _locator_from_read_model(value: Any) -> SourceLocator:
    location = getattr(value, "location", None)
    if location is not None:
        return SourceLocator(
            page=location.page,
            slide=location.slide,
            sheet=location.sheet,
            cell_range=location.cell_range,
            section_path=location.section_path,
            paragraph_index=location.paragraph_index,
            table_index=location.table_index,
            block_index=location.block_index,
        )
    return SourceLocator(
        page=getattr(value, "page", None),
        slide=getattr(value, "slide", None),
        sheet=getattr(value, "sheet", None),
        cell_range=getattr(value, "cell_range", None),
        section_path=getattr(value, "section_path", None),
        paragraph_index=getattr(value, "paragraph_index", None),
        table_index=getattr(value, "table_index", None),
        block_index=getattr(value, "block_index", None),
    )
