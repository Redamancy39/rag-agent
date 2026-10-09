from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document_collection import DocumentCollection
    from app.models.document_job import DocumentProcessingJob
    from app.models.group import GroupPermission
    from app.models.permission import Permission
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    file_type: Mapped[str] = mapped_column(String(32), index=True)
    content_type: Mapped[str | None] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    status_message: Mapped[str | None] = mapped_column(String(512))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_collections.id"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    owner: Mapped["User"] = relationship(back_populates="documents")
    collection: Mapped["DocumentCollection | None"] = relationship(
        back_populates="documents"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    group_permissions: Mapped[list["GroupPermission"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    processing_jobs: Mapped[list["DocumentProcessingJob"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    @property
    def owner_username(self) -> str | None:
        return self.owner.username if self.owner else None

    @property
    def collection_name(self) -> str | None:
        return self.collection.name if self.collection else None
