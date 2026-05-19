from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_permission_document_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped["Document"] = relationship(back_populates="permissions")
    user: Mapped["User"] = relationship(back_populates="permissions")

    @property
    def user_username(self) -> str | None:
        return self.user.username if self.user else None
