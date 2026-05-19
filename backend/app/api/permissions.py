from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.session import get_db
from app.models.group import AuditLog, Group, GroupPermission, UserGroup
from app.models.permission import Permission
from app.models.user import User
from app.schemas.permission import (
    AuditLogRead,
    GroupCreate,
    GroupPermissionCreate,
    GroupPermissionRead,
    GroupRead,
    GroupUpdate,
    PermissionCreate,
    PermissionRead,
    UserGroupCreate,
    UserGroupRead,
)
from app.services import permission_service

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/", response_model=list[PermissionRead])
def list_permissions(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Permission]:
    return permission_service.list_permissions(db)


@router.get("/documents/{document_id}", response_model=list[PermissionRead])
def list_document_permissions(
    document_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Permission]:
    return permission_service.list_document_permissions(db, document_id)


@router.post("/", response_model=PermissionRead)
def upsert_permission(
    payload: PermissionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Permission:
    try:
        return permission_service.upsert_permission(db, payload, actor=current_user)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc) or "Failed to save permission",
        ) from exc


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(
    permission_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = permission_service.delete_permission(db, permission_id, actor=current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found",
        )


@router.get("/groups", response_model=list[GroupRead])
def list_groups(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Group]:
    return permission_service.list_groups(db)


@router.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: GroupCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Group:
    try:
        return permission_service.create_group(db, payload, actor=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group(
    group_id: int,
    payload: GroupUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Group:
    try:
        group = permission_service.update_group(db, group_id, payload, actor=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = permission_service.delete_group(db, group_id, actor=current_user)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")


@router.get("/groups/{group_id}/members", response_model=list[UserGroupRead])
def list_group_members(
    group_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[UserGroup]:
    return permission_service.list_group_members(db, group_id)


@router.post("/groups/{group_id}/members", response_model=UserGroupRead)
def add_group_member(
    group_id: int,
    payload: UserGroupCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserGroup:
    try:
        return permission_service.add_group_member(
            db,
            group_id,
            payload.user_id,
            actor=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: int,
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = permission_service.remove_group_member(
        db,
        group_id,
        user_id,
        actor=current_user,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found")


@router.get(
    "/documents/{document_id}/group-permissions",
    response_model=list[GroupPermissionRead],
)
def list_document_group_permissions(
    document_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[GroupPermission]:
    return permission_service.list_document_group_permissions(db, document_id)


@router.post("/group-permissions", response_model=GroupPermissionRead)
def upsert_group_permission(
    payload: GroupPermissionCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GroupPermission:
    try:
        return permission_service.upsert_group_permission(db, payload, actor=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/group-permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group_permission(
    permission_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    deleted = permission_service.delete_group_permission(db, permission_id, actor=current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group permission not found",
        )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLog]:
    return permission_service.list_audit_logs(db, limit=limit)
