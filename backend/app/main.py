from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    chat,
    document_collections,
    documents,
    evaluations,
    logs,
    permissions,
    users,
)
from app.core.config import get_settings
from app.core.logger import configure_logging, get_logger
from app.core.native_runtime import prepare_torch_runtime
from app.db.init_db import init_db

settings = get_settings()
configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Multi-user RAG Agent knowledge base system.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(documents.router, prefix=settings.API_V1_PREFIX)
app.include_router(document_collections.router, prefix=settings.API_V1_PREFIX)
app.include_router(permissions.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(logs.router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluations.router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def on_startup() -> None:
    if prepare_torch_runtime():
        logger.info('PyTorch native runtime loaded before OCR')
    init_db()
    logger.info("Backend started")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": settings.PROJECT_NAME}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
