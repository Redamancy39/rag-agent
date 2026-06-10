from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str | None] = mapped_column(Text)
    retrieval_trace_json: Mapped[str | None] = mapped_column(Text)
    query_plan_json: Mapped[str | None] = mapped_column(Text)
    evidence_decision_json: Mapped[str | None] = mapped_column(Text)
    citation_validation_json: Mapped[str | None] = mapped_column(Text)
    retrieval_scope_json: Mapped[str | None] = mapped_column(Text)
    response_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship(back_populates="chat_logs")
