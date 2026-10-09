"""Immutable, per-question retrieval settings; never mutate shared configuration."""
from pydantic import BaseModel, ConfigDict, Field


class RetrievalOptions(BaseModel):
    top_k: int = Field(default=5, ge=5, le=40)
    rerank_enabled: bool = True
    candidate_top_k: int | None = Field(default=None, ge=16, le=128)
    context_auto: bool = True
    context_max_chars: int = Field(default=16000, ge=8000, le=64000)


class ResolvedRetrievalOptions(BaseModel):
    model_config = ConfigDict(frozen=True)
    top_k: int
    rerank_enabled: bool
    candidate_top_k: int
    context_auto: bool
    context_max_chars: int
    model_context_tokens: int
    output_reserve_ratio: float
    max_output_tokens: int


def resolve_retrieval_options(options: RetrievalOptions, settings) -> ResolvedRetrievalOptions:
    return ResolvedRetrievalOptions(
        top_k=options.top_k, rerank_enabled=options.rerank_enabled,
        candidate_top_k=max(options.top_k, options.candidate_top_k or max(32, options.top_k * 2)),
        context_auto=options.context_auto,
        context_max_chars=max(16000, options.top_k * 1200) if options.context_auto else options.context_max_chars,
        model_context_tokens=getattr(settings, 'QA_MODEL_CONTEXT_TOKENS', 1048576),
        output_reserve_ratio=getattr(settings, 'QA_OUTPUT_RESERVE_RATIO', 0.30),
        max_output_tokens=min(getattr(settings, 'QA_MAX_OUTPUT_TOKENS', 65536),
                              getattr(settings, 'QA_MODEL_MAX_OUTPUT_TOKENS', 393216)),
    )
