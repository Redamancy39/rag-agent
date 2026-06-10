import json
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.models.chat_log import ChatLog
from app.models.user import User
from app.schemas.chat import (
    ChatLogRead,
    ChatResponse,
    Citation,
    CitationValidationRead,
    EvidenceDecisionRead,
    QueryPlanRead,
    RetrievalScopeRead,
    RetrievalTraceStep,
)

logger = get_logger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


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
    response: ChatResponse,
) -> ChatLog | None:
    chat_log = ChatLog(
        user_id=user.id,
        question=question,
        answer=response.answer,
        citations_json=_dump_models(response.citations),
        retrieval_trace_json=_dump_models(response.retrieval_trace),
        query_plan_json=_dump_model(response.query_plan),
        evidence_decision_json=_dump_model(response.evidence_decision),
        citation_validation_json=_dump_model(response.citation_validation),
        retrieval_scope_json=_dump_model(response.retrieval_scope),
        response_json=json.dumps(response.model_dump(mode="json"), ensure_ascii=False),
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


def chat_log_to_read(chat_log: ChatLog) -> ChatLogRead:
    citations = _load_model_list(chat_log.citations_json, Citation)
    retrieval_trace = _load_model_list(
        chat_log.retrieval_trace_json,
        RetrievalTraceStep,
    )
    query_plan = _load_model(chat_log.query_plan_json, QueryPlanRead)
    evidence_decision = _load_model(
        chat_log.evidence_decision_json,
        EvidenceDecisionRead,
    )
    citation_validation = _load_model(
        chat_log.citation_validation_json,
        CitationValidationRead,
    ) or CitationValidationRead(
        valid=True,
        cited_indices=[
            citation.citation_id or index
            for index, citation in enumerate(citations, start=1)
        ],
    )
    retrieval_scope = _load_model(
        chat_log.retrieval_scope_json,
        RetrievalScopeRead,
    ) or RetrievalScopeRead()
    response = _load_model(chat_log.response_json, ChatResponse)

    if response is None:
        response = ChatResponse(
            answer=chat_log.answer,
            citations=citations,
            retrieval_trace=retrieval_trace,
            query_plan=query_plan,
            evidence_decision=evidence_decision,
            citation_validation=citation_validation,
            retrieval_scope=retrieval_scope,
        )
    response.log_id = chat_log.id

    return ChatLogRead(
        id=chat_log.id,
        user_id=chat_log.user_id,
        question=chat_log.question,
        answer=chat_log.answer,
        citations_json=chat_log.citations_json,
        retrieval_trace=response.retrieval_trace,
        query_plan=response.query_plan,
        evidence_decision=response.evidence_decision,
        citation_validation=response.citation_validation,
        retrieval_scope=response.retrieval_scope,
        response=response,
        created_at=chat_log.created_at,
    )


def _dump_models(values: list[BaseModel]) -> str:
    return json.dumps(
        [value.model_dump(mode="json") for value in values],
        ensure_ascii=False,
    )


def _dump_model(value: BaseModel | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _load_model(value: str | None, model_type: type[ModelT]) -> ModelT | None:
    payload = _load_json(value)
    if not isinstance(payload, dict):
        return None
    try:
        return model_type.model_validate(payload)
    except Exception:
        return None


def _load_model_list(value: str | None, model_type: type[ModelT]) -> list[ModelT]:
    payload = _load_json(value)
    if not isinstance(payload, list):
        return []
    result: list[ModelT] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            result.append(model_type.model_validate(item))
        except Exception:
            continue
    return result
