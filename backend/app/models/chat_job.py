from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatJob(Base):
    __tablename__ = "chat_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    message: Mapped[str | None] = mapped_column(String(512))
    error_message: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    document_ids_json: Mapped[str | None] = mapped_column(Text)
    top_k: Mapped[int] = mapped_column(Integer, default=6)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_detail: Mapped[str | None] = mapped_column(String(512))
    trace_json: Mapped[str | None] = mapped_column(Text)
    response_json: Mapped[str | None] = mapped_column(Text)
    log_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
