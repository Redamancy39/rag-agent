from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    members: Mapped[list["UserGroup"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    permissions: Mapped[list["GroupPermission"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class UserGroup(Base):
    __tablename__ = "user_groups"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_user_group_group_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    group: Mapped["Group"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="group_memberships")

    @property
    def group_name(self) -> str | None:
        return self.group.name if self.group else None

    @property
    def user_username(self) -> str | None:
        return self.user.username if self.user else None


class GroupPermission(Base):
    __tablename__ = "group_permissions"
    __table_args__ = (
        UniqueConstraint("document_id", "group_id", name="uq_group_permission_document_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped["Document"] = relationship(back_populates="group_permissions")
    group: Mapped["Group"] = relationship(back_populates="permissions")

    @property
    def group_name(self) -> str | None:
        return self.group.name if self.group else None


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(96), index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, index=True)
    document_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    group_id: Mapped[int | None] = mapped_column(Integer, index=True)
    detail_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
