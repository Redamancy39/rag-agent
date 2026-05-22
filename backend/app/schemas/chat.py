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


class ChatResponse(BaseModel):
    answer: str
    sections: AnswerSections = Field(default_factory=AnswerSections)
    evidence_rows: list[EvidenceRow] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
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
