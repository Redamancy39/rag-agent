from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.user import User
from app.schemas.chat import ChatJobRead, ChatLogRead, ChatRequest, ChatResponse
from app.services import chat_job_service, log_service
from app.services.rag_service import RagService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    return RagService().answer(
        db,
        user=current_user,
        question=payload.question,
        requested_document_ids=payload.document_ids,
        top_k=payload.top_k,
    )


@router.post("/jobs", response_model=ChatJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_chat_job(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatJobRead:
    job = chat_job_service.create_chat_job(
        db,
        user=current_user,
        question=payload.question,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
    chat_job_service.start_chat_job(job.id)
    return ChatJobRead.model_validate(job)


@router.get("/jobs/{job_id}", response_model=ChatJobRead)
def read_chat_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatJobRead:
    job = chat_job_service.get_user_chat_job(db, user=current_user, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat job not found")
    return ChatJobRead.model_validate(job)


@router.get("/history", response_model=list[ChatLogRead])
def chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChatLog]:
    return log_service.list_user_chat_logs(db, current_user, limit=limit)


@router.delete("/history/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_history(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not log_service.delete_user_chat_log(db, current_user, log_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat log not found")
