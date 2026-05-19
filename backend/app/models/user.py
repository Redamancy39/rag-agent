from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.chat_log import ChatLog
    from app.models.document import Document
    from app.models.group import UserGroup
    from app.models.permission import Permission


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="owner")
    permissions: Mapped[list["Permission"]] = relationship(back_populates="user")
    group_memberships: Mapped[list["UserGroup"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    chat_logs: Mapped[list["ChatLog"]] = relationship(back_populates="user")
