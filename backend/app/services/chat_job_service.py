import json
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.models.chat_job import ChatJob
from app.models.user import User
from app.services.rag_service import RagService
from app.rag.retrieval_options import ResolvedRetrievalOptions

logger = get_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_chat_job(
    db: Session,
    *,
    user: User,
    question: str,
    document_ids: list[int] | None,
    top_k: int,
    retrieval_options: ResolvedRetrievalOptions | None = None,
) -> ChatJob:
    job = ChatJob(
        user_id=user.id,
        status="queued",
        stage="queued",
        message="问答任务已创建，等待执行",
        question=question,
        document_ids_json=json.dumps(document_ids or [], ensure_ascii=False),
        top_k=top_k,
        retrieval_options_json=retrieval_options.model_dump_json() if retrieval_options else None,
        progress_percent=1,
        progress_detail="等待执行",
        trace_json=json.dumps(
            [
                {
                    "stage": "queued",
                    "message": "问答任务已创建，等待执行",
                    "progress": 1,
                    "timestamp": utc_now().isoformat(),
                }
            ],
            ensure_ascii=False,
        ),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_user_chat_job(db: Session, *, user: User, job_id: int) -> ChatJob | None:
    return db.scalar(
        select(ChatJob).where(ChatJob.id == job_id, ChatJob.user_id == user.id)
    )


def start_chat_job(job_id: int) -> None:
    worker = threading.Thread(
        target=run_chat_job,
        args=(job_id,),
        name=f"chat-job-{job_id}",
        daemon=True,
    )
    worker.start()


def run_chat_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(ChatJob, job_id)
        if not job:
            logger.warning("Chat job id=%s not found", job_id)
            return
        user = db.get(User, job.user_id)
        if not user:
            _finish_failed_job(db, job, "任务用户不存在")
            return

        job.status = "running"
        job.stage = "started"
        job.message = "高可靠 RAG 问答开始执行"
        job.progress_percent = 3
        job.progress_detail = "初始化权限约束与检索链路"
        job.started_at = utc_now()
        _append_trace(job, {"stage": "started", "message": job.message, "progress": 3})
        db.commit()

        document_ids = _parse_document_ids(job.document_ids_json)

        def progress_callback(event: dict) -> None:
            _update_progress_from_event(db, job, event)

        try:
            response = RagService().answer(
                db,
                user=user,
                question=job.question,
                requested_document_ids=document_ids or None,
                top_k=job.top_k,
                retrieval_options=(ResolvedRetrievalOptions.model_validate_json(job.retrieval_options_json)
                                   if job.retrieval_options_json else None),
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.exception("Chat job id=%s failed", job_id)
            _finish_failed_job(db, job, str(exc))
            return

        job.status = "completed"
        job.stage = "completed"
        job.message = "问答任务完成"
        job.progress_percent = 100
        job.progress_detail = "答案已生成"
        job.response_json = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
        job.log_id = response.log_id
        job.finished_at = utc_now()
        _append_trace(
            job,
            {
                "stage": "completed",
                "message": "问答任务完成",
                "progress": 100,
                "log_id": response.log_id,
            },
        )
        db.commit()


def _update_progress_from_event(db: Session, job: ChatJob, event: dict[str, Any]) -> None:
    stage = str(event.get("stage") or job.stage or "running")
    message = str(event.get("message") or job.message or "问答任务执行中")
    progress = _coerce_percent(event.get("progress"), job.progress_percent)
    job.status = "running"
    job.stage = stage
    job.message = message
    job.progress_percent = progress
    job.progress_detail = message
    _append_trace(job, event)
    db.commit()


def _finish_failed_job(db: Session, job: ChatJob, error_message: str) -> None:
    job.status = "failed"
    job.stage = "failed"
    job.message = "问答任务失败"
    job.error_message = error_message
    job.progress_percent = 100
    job.progress_detail = error_message
    job.finished_at = utc_now()
    _append_trace(
        job,
        {
            "stage": "failed",
            "message": "问答任务失败",
            "progress": 100,
            "error_message": error_message,
        },
    )
    db.commit()


def _append_trace(job: ChatJob, event: dict[str, Any]) -> None:
    trace = _parse_trace(job.trace_json)
    item = dict(event)
    item.setdefault("timestamp", utc_now().isoformat())
    trace.append(item)
    job.trace_json = json.dumps(trace[-120:], ensure_ascii=False)


def _parse_trace(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [{"raw": value}]
    if isinstance(parsed, list):
        return [item if isinstance(item, dict) else {"value": item} for item in parsed]
    return [{"value": parsed}]


def _parse_document_ids(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    document_ids: list[int] = []
    for item in parsed:
        try:
            document_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return document_ids


def _coerce_percent(value: object, default: int) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = default
    return max(0, min(100, percent))
