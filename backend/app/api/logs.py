from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.user import User
from app.schemas.chat import ChatLogRead
from app.services import log_service

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/chat", response_model=list[ChatLogRead])
def list_chat_logs(
    _: User = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ChatLog]:
    return log_service.list_chat_logs(db, limit=limit)
