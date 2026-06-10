from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.group import Group
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentCollection(Base):
    __tablename__ = "document_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(512))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    owner: Mapped["User"] = relationship(back_populates="owned_document_collections")
    documents: Mapped[list["Document"]] = relationship(back_populates="collection")
    user_permissions: Mapped[list["CollectionUserPermission"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
    )
    group_permissions: Mapped[list["CollectionGroupPermission"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
    )

    @property
    def owner_username(self) -> str | None:
        return self.owner.username if self.owner else None


class CollectionUserPermission(Base):
    __tablename__ = "collection_user_permissions"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "user_id",
            name="uq_collection_user_permission_collection_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("document_collections.id"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    collection: Mapped["DocumentCollection"] = relationship(
        back_populates="user_permissions"
    )
    user: Mapped["User"] = relationship(back_populates="collection_permissions")

    @property
    def user_username(self) -> str | None:
        return self.user.username if self.user else None


class CollectionGroupPermission(Base):
    __tablename__ = "collection_group_permissions"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "group_id",
            name="uq_collection_group_permission_collection_group",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("document_collections.id"),
        index=True,
    )
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    collection: Mapped["DocumentCollection"] = relationship(
        back_populates="group_permissions"
    )
    group: Mapped["Group"] = relationship(back_populates="collection_permissions")

    @property
    def group_name(self) -> str | None:
        return self.group.name if self.group else None
