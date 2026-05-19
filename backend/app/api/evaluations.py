from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.evaluation import RagEvalRunRequest, RagEvalRunResponse
from app.services.evaluation_service import run_rag_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/rag", response_model=RagEvalRunResponse)
def run_rag_eval(
    payload: RagEvalRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagEvalRunResponse:
    return run_rag_evaluation(db, user=current_user, request=payload)
