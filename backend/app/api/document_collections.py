from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.db.session import get_db
from app.models.document_collection import (
    CollectionGroupPermission,
    CollectionUserPermission,
)
from app.models.user import User
from app.schemas.document_collection import (
    CollectionGroupPermissionCreate,
    CollectionGroupPermissionRead,
    CollectionUserPermissionCreate,
    CollectionUserPermissionRead,
    DocumentCollectionCreate,
    DocumentCollectionMoveRequest,
    DocumentCollectionMoveResult,
    DocumentCollectionRead,
    DocumentCollectionUpdate,
)
from app.services import document_collection_service

router = APIRouter(prefix="/document-collections", tags=["document-collections"])


@router.get("/", response_model=list[DocumentCollectionRead])
def list_document_collections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return document_collection_service.list_accessible_collections(db, current_user)


@router.post(
    "/",
    response_model=DocumentCollectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document_collection(
    payload: DocumentCollectionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return document_collection_service.create_collection(
            db,
            payload,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/move-documents", response_model=DocumentCollectionMoveResult)
def move_documents(
    payload: DocumentCollectionMoveRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return document_collection_service.move_documents(
            db,
            payload.document_ids,
            payload.collection_id,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{collection_id}", response_model=DocumentCollectionRead)
def update_document_collection(
    collection_id: int,
    payload: DocumentCollectionUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        collection = document_collection_service.update_collection(
            db,
            collection_id,
            payload,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document collection not found",
        )
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_collection(
    collection_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = document_collection_service.delete_collection(
        db,
        collection_id,
        actor=current_user,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document collection not found",
        )


@router.get(
    "/{collection_id}/user-permissions",
    response_model=list[CollectionUserPermissionRead],
)
def list_collection_user_permissions(
    collection_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CollectionUserPermission]:
    return document_collection_service.list_user_permissions(db, collection_id)


@router.post(
    "/{collection_id}/user-permissions",
    response_model=CollectionUserPermissionRead,
)
def upsert_collection_user_permission(
    collection_id: int,
    payload: CollectionUserPermissionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CollectionUserPermission:
    try:
        return document_collection_service.upsert_user_permission(
            db,
            collection_id,
            payload,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/user-permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection_user_permission(
    permission_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = document_collection_service.delete_user_permission(
        db,
        permission_id,
        actor=current_user,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")


@router.get(
    "/{collection_id}/group-permissions",
    response_model=list[CollectionGroupPermissionRead],
)
def list_collection_group_permissions(
    collection_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CollectionGroupPermission]:
    return document_collection_service.list_group_permissions(db, collection_id)


@router.post(
    "/{collection_id}/group-permissions",
    response_model=CollectionGroupPermissionRead,
)
def upsert_collection_group_permission(
    collection_id: int,
    payload: CollectionGroupPermissionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CollectionGroupPermission:
    try:
        return document_collection_service.upsert_group_permission(
            db,
            collection_id,
            payload,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete(
    "/group-permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection_group_permission(
    permission_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = document_collection_service.delete_group_permission(
        db,
        permission_id,
        actor=current_user,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
