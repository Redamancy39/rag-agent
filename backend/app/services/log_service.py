import json

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.chat_log import ChatLog
from app.models.user import User
from app.schemas.chat import Citation

logger = get_logger(__name__)


def list_chat_logs(db: Session, limit: int = 100) -> list[ChatLog]:
    statement = select(ChatLog).order_by(ChatLog.id.desc()).limit(limit)
    return list(db.scalars(statement))


def list_user_chat_logs(db: Session, user: User, limit: int = 50) -> list[ChatLog]:
    statement = (
        select(ChatLog)
        .where(ChatLog.user_id == user.id)
        .order_by(ChatLog.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def delete_user_chat_log(db: Session, user: User, log_id: int) -> bool:
    statement = select(ChatLog).where(ChatLog.id == log_id, ChatLog.user_id == user.id)
    chat_log = db.scalar(statement)
    if not chat_log:
        return False
    db.delete(chat_log)
    try:
        db.commit()
        return True
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Failed to delete chat log id=%s: %s", log_id, exc)
        return False


def create_chat_log(
    db: Session,
    *,
    user: User,
    question: str,
    answer: str,
    citations: list[Citation],
) -> ChatLog | None:
    chat_log = ChatLog(
        user_id=user.id,
        question=question,
        answer=answer,
        citations_json=json.dumps(
            [citation.model_dump() for citation in citations],
            ensure_ascii=False,
        ),
    )
    db.add(chat_log)
    try:
        db.commit()
        db.refresh(chat_log)
        return chat_log
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Failed to write chat log: %s", exc)
        return None
