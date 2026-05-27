from pydantic import BaseModel, Field

from app.schemas.chat import ChatResponse


class RagEvalCase(BaseModel):
    id: str
    question: str = Field(min_length=1, max_length=4000)
    expected_found: bool = True
    expected_answer_keywords: list[str] = Field(default_factory=list)
    expected_citation_keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    document_ids: list[int] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RagEvalRunRequest(BaseModel):
    name: str = "manual-rag-eval"
    cases: list[RagEvalCase]


class RagEvalCaseResult(BaseModel):
    id: str
    question: str
    tags: list[str] = Field(default_factory=list)
    passed: bool
    expected_found: bool
    actual_found: bool
    missing_answer_keywords: list[str]
    missing_citation_keywords: list[str]
    response: ChatResponse


class RagEvalRunResponse(BaseModel):
    name: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    results: list[RagEvalCaseResult]
