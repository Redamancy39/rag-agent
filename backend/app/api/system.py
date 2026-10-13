import os

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.models.user import User

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info")
def system_info(_current_user: User = Depends(get_current_user)) -> dict[str, str | bool | None]:
    settings = get_settings()
    mode = os.environ.get("LOCAL_LLM_MODE") or "offline"
    if mode not in {"offline", "chat", "chat_and_normalization"}:
        mode = "offline"
    return {
        "llm_mode": mode,
        "llm_model": settings.OPENAI_MODEL_NAME,
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
        "reranker_enabled": settings.RERANKER_ENABLED,
        "reranker_model": settings.RERANKER_MODEL_NAME,
        "agentic_rag_enabled": settings.AGENTIC_RAG_ENABLED,
        "ocr_enabled": bool(settings.LITEPARSE_OCR_ENABLED or settings.PREPROCESS_OCR_FALLBACK_ENABLED),
    }
