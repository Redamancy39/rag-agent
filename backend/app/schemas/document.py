import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    content_type: str | None
    storage_path: str
    file_size: int
    status: str
    status_message: str | None = None
    chunk_count: int
    error_message: str | None
    owner_id: int
    owner_username: str | None = None
    created_at: datetime
    updated_at: datetime | None


class DocumentChunkRead(BaseModel):
    id: str
    text: str
    metadata: dict


class DocumentProcessingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    status: str
    stage: str
    message: str | None
    error_message: str | None
    probe_json: dict[str, Any] | None = None
    plan_json: dict[str, Any] | None = None
    options_json: dict[str, Any] | None = None
    progress_total: int = 0
    progress_current: int = 0
    progress_percent: int = 0
    progress_detail: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None

    @field_validator("probe_json", "plan_json", "options_json", mode="before")
    @classmethod
    def parse_json_field(cls, value: Any) -> dict[str, Any] | None:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"raw": value}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        return None


class DocumentQualityReportRead(BaseModel):
    document_id: int
    filename: str
    status: str
    status_message: str | None = None
    total_chunks: int
    unique_pages: int
    chunk_type_counts: dict[str, int]
    quality_counts: dict[str, int]
    average_quality_score: float | None = None
    health_score: int = 0
    risk_level: str = "unknown"
    risk_items: list[str] = []
    low_quality_count: int
    ocr_chunk_count: int
    ocr_average_score: float | None = None
    bad_text_layer_count: int = 0
    ocr_replaced_bad_text_layer_count: int = 0
    preprocess_repair_count: int = 0
    suspicious_power_notation_count: int = 0
    table_chunk_count: int
    llm_normalized_count: int
    llm_candidate_count: int
    latest_job_stage: str | None = None
    latest_job_message: str | None = None
    latest_job_progress_current: int = 0
    latest_job_progress_total: int = 0
    latest_job_progress_percent: int = 0
    stage_overview: list[dict[str, Any]] = []
    recommendations: list[str]
