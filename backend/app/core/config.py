import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "RAG Agent KB System"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    SECRET_KEY: str = "change-this-secret-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    DATABASE_URL: str = Field(
        default_factory=lambda: f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
    )
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    CHROMA_DIR: Path = DATA_DIR / "chroma"
    CHROMA_COLLECTION_NAME: str = "knowledge_chunks"
    LOG_DIR: Path = DATA_DIR / "logs"

    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DEVICE: str = "auto"
    EMBEDDING_BATCH_SIZE: int = 16
    RERANKER_MODEL_NAME: str | None = None
    RERANKER_ENABLED: bool = True
    RERANKER_DEVICE: str = "auto"
    RERANKER_CANDIDATE_TOP_K: int = 20
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_FILE_EXTENSIONS: list[str] = [".txt", ".md", ".markdown", ".pdf"]

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = "https://api.deepseek.com"
    OPENAI_MODEL_NAME: str | None = "deepseek-v4-flash"

    PREPROCESS_LLM_ENABLED: bool = False
    PREPROCESS_LLM_TARGET_CHUNK_TYPES: list[str] = ["table_row_fact"]
    PREPROCESS_LLM_MAX_INPUT_CHARS: int = 4000
    PREPROCESS_LLM_TIMEOUT_SECONDS: float = 60.0
    PREPROCESS_LOCAL_BAD_PAGE_OCR_ENABLED: bool = True
    PREPROCESS_DROP_BAD_TEXT_LAYER_WHEN_OCR_AVAILABLE: bool = True
    PREPROCESS_TEXT_REPAIR_ENABLED: bool = True
    CHUNK_QUALITY_ENABLED: bool = True
    CHUNK_LLM_NORMALIZATION_ENABLED: bool = True
    CHUNK_LLM_MIN_QUALITY_SCORE: float = 0.82
    CHUNK_LLM_MIN_CHUNKS_PER_DOCUMENT: int = 20
    CHUNK_LLM_MAX_CHUNKS_PER_DOCUMENT: int = 120
    CHUNK_LLM_CANDIDATE_RATIO: float = 0.3
    CHUNK_LLM_SKIP_ALREADY_NORMALIZED_SOURCES: bool = True
    CHUNK_LLM_MERGE_MODE: str = "replace_source"
    CHUNK_LLM_MIN_INPUT_CHARS: int = 20

    INGESTION_AGENT_ENABLED: bool = True
    INGESTION_AGENT_LLM_ENABLED: bool = False
    INGESTION_AGENT_SAMPLE_PAGES: int = 3
    INGESTION_MAX_CONCURRENT_JOBS: int = 1
    RELEASE_GPU_CACHE_AFTER_INGESTION: bool = True

    PREPROCESS_OCR_FALLBACK_ENABLED: bool = False
    OCR_MIN_EXTRACTED_CHARS: int = 50
    OCR_MAX_PAGES: int | None = None
    PDF_REJECT_GARBLED_TEXT: bool = True

    RAG_TOP_K: int = 5
    RAG_CONTEXT_MAX_CHARS: int = 6000
    RAG_MIN_SCORE: float = 0.35
    RAG_MIN_READABLE_CHARS: int = 30
    RAG_MAX_GARBLED_TOKEN_RATIO: float = 0.08
    RAG_CHAIN_RETRIEVAL_ENABLED: bool = True
    RAG_CHAIN_MAX_QUERIES: int = 4
    RAG_CHAIN_PER_QUERY_TOP_K: int = 8
    RAG_CHAIN_EXPANSION_SCORE_FACTOR: float = 0.97
    HYBRID_RETRIEVAL_ENABLED: bool = True
    HYBRID_KEYWORD_CANDIDATE_TOP_K: int = 20
    HYBRID_KEYWORD_MAX_CHUNKS: int = 3000
    HYBRID_BM25_ENABLED: bool = True
    HYBRID_BM25_CANDIDATE_TOP_K: int = 12
    HYBRID_BM25_MAX_CHUNKS: int = 3000
    HYBRID_BM25_K1: float = 1.5
    HYBRID_BM25_B: float = 0.75
    HYBRID_VECTOR_WEIGHT: float = 0.62
    HYBRID_KEYWORD_WEIGHT: float = 0.08
    HYBRID_BM25_WEIGHT: float = 0.30
    HYBRID_LEXICAL_ONLY_MAX_SCORE: float = 0.82

    OCR_DETECTION_MODEL_DIR: Path | None = None
    OCR_RECOGNITION_MODEL_DIR: Path | None = None
    OCR_TEXTLINE_ORIENTATION_MODEL_DIR: Path | None = None
    PADDLEOCR_DEVICE: str = "cpu"
    PADDLEOCR_USE_TEXTLINE_ORIENTATION: bool = False
    PADDLEOCR_USE_SUBPROCESS: bool = True

    FIRST_SUPERUSER_USERNAME: str | None = None
    FIRST_SUPERUSER_PASSWORD: str | None = None

    LOG_LEVEL: str = "INFO"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return _parse_str_list(value)
        return value

    @field_validator("ALLOWED_FILE_EXTENSIONS", mode="before")
    @classmethod
    def parse_allowed_file_extensions(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.lower() for item in _parse_str_list(value)]
        return value

    @field_validator("PREPROCESS_LLM_TARGET_CHUNK_TYPES", mode="before")
    @classmethod
    def parse_preprocess_llm_target_chunk_types(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return _parse_str_list(value)
        return value

    @field_validator("OCR_MAX_PAGES", mode="before")
    @classmethod
    def parse_ocr_max_pages(cls, value: Any) -> int | None:
        if value in {None, ""}:
            return None
        return int(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _parse_str_list(value: str) -> list[str]:
    stripped = value.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in stripped.split(",") if item.strip()]
