from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_ids: list[int] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class Citation(BaseModel):
    document_id: int
    filename: str
    chunk_id: str | None = None
    page: int | None = None
    table: str | None = None
    chunk_type: str | None = None
    score: float | None = None
    text: str


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
    table: str | None = None
    chunk_id: str | None = None
    keywords: str


class RetrievalTraceHit(BaseModel):
    rank: int
    score: float | None = None
    filename: str
    page: int | None = None
    table: str | None = None
    chunk_id: str | None = None
    retrieval_source: str | None = None
    matched_terms: list[str] = Field(default_factory=list)


class RetrievalTraceStep(BaseModel):
    query_index: int
    query: str
    source: str
    hit_count: int
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


class ChatResponse(BaseModel):
    answer: str
    sections: AnswerSections = Field(default_factory=AnswerSections)
    evidence_rows: list[EvidenceRow] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    retrieval_trace: list[RetrievalTraceStep] = Field(default_factory=list)
    query_plan: QueryPlanRead | None = None
    evidence_decision: EvidenceDecisionRead | None = None
    retrieval_only: bool = False
    log_id: int | None = None


class ChatLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    question: str
    answer: str
    citations_json: str | None
    created_at: datetime
