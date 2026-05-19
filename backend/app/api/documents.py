from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    DocumentChunkRead,
    DocumentProcessingJobRead,
    DocumentQualityReportRead,
    DocumentRead,
)
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=list[DocumentRead])
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Document]:
    return document_service.list_accessible_documents(db, current_user)


@router.get("/{document_id}", response_model=DocumentRead)
def read_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    document = document_service.get_accessible_document(db, document_id, current_user)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )
    return document


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkRead])
def read_document_chunks(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    try:
        chunks = document_service.list_document_chunks(
            db,
            document_id=document_id,
            user=current_user,
            limit=limit,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    if chunks is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )
    return chunks


@router.get("/{document_id}/jobs", response_model=list[DocumentProcessingJobRead])
def read_document_jobs(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    jobs = document_service.list_document_jobs(db, document_id, current_user)
    if jobs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )
    return jobs


@router.get("/{document_id}/quality-report", response_model=DocumentQualityReportRead)
def read_document_quality_report(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        report = document_service.get_document_quality_report(db, document_id, current_user)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or not accessible",
        )
    return report


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    enable_llm_chunk_normalization: bool | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    try:
        document = await document_service.create_document_record(
            db,
            current_user,
            file,
            enable_llm_chunk_normalization=enable_llm_chunk_normalization,
        )
        background_tasks.add_task(document_service.index_document_by_id, document.id)
        return document
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/{document_id}/normalize-chunks", response_model=DocumentRead)
def normalize_document_chunks(
    document_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    try:
        document = document_service.queue_document_chunk_normalization(
            db,
            document_id=document_id,
            user=current_user,
        )
        background_tasks.add_task(document_service.normalize_document_chunks_by_id, document.id)
        return document
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        deleted = document_service.delete_document_as_admin(db, document_id, current_user)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
