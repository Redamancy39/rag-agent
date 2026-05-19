import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.group import AuditLog, Group, GroupPermission, UserGroup
from app.models.permission import Permission
from app.models.user import User
from app.schemas.permission import GroupCreate, GroupPermissionCreate, GroupUpdate, PermissionCreate


def list_permissions(db: Session) -> list[Permission]:
    return list(
        db.scalars(
            select(Permission)
            .options(selectinload(Permission.user))
            .order_by(Permission.id.desc())
        )
    )


def list_document_permissions(db: Session, document_id: int) -> list[Permission]:
    return list(
        db.scalars(
            select(Permission)
            .options(selectinload(Permission.user))
            .where(Permission.document_id == document_id)
            .order_by(Permission.id.desc())
        )
    )


def upsert_permission(
    db: Session,
    permission_in: PermissionCreate,
    *,
    actor: User | None = None,
) -> Permission:
    document = db.get(Document, permission_in.document_id)
    if not document:
        raise ValueError("Document not found")
    user = db.get(User, permission_in.user_id)
    if not user:
        raise ValueError("User not found")
    if document.owner_id == permission_in.user_id:
        raise ValueError("Document owner already has access")

    permission = db.scalar(
        select(Permission).where(
            Permission.document_id == permission_in.document_id,
            Permission.user_id == permission_in.user_id,
        )
    )
    if permission:
        permission.can_read = permission_in.can_read
        permission.can_write = permission_in.can_write
        action = "permission.user.updated"
    else:
        permission = Permission(**permission_in.model_dump())
        db.add(permission)
        action = "permission.user.created"

    db.commit()
    db.refresh(permission)
    permission.user = user
    write_audit_log(
        db,
        actor=actor,
        action=action,
        target_type="permission",
        target_id=permission.id,
        document_id=permission.document_id,
        user_id=permission.user_id,
        detail={
            "can_read": permission.can_read,
            "can_write": permission.can_write,
            "username": user.username,
            "document_filename": document.filename,
        },
    )
    return permission


def delete_permission(db: Session, permission_id: int, *, actor: User | None = None) -> bool:
    permission = db.get(Permission, permission_id)
    if not permission:
        return False
    document_id = permission.document_id
    user_id = permission.user_id
    detail = {
        "can_read": permission.can_read,
        "can_write": permission.can_write,
    }
    db.delete(permission)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="permission.user.deleted",
        target_type="permission",
        target_id=permission_id,
        document_id=document_id,
        user_id=user_id,
        detail=detail,
    )
    return True


def list_groups(db: Session) -> list[Group]:
    return list(db.scalars(select(Group).order_by(Group.id.desc())))


def create_group(db: Session, payload: GroupCreate, *, actor: User | None = None) -> Group:
    name = payload.name.strip()
    if not name:
        raise ValueError("Group name is required")
    existing = db.scalar(select(Group).where(Group.name == name))
    if existing:
        raise ValueError("Group name already exists")
    group = Group(name=name, description=payload.description)
    db.add(group)
    db.commit()
    db.refresh(group)
    write_audit_log(
        db,
        actor=actor,
        action="group.created",
        target_type="group",
        target_id=group.id,
        group_id=group.id,
        detail={"name": group.name, "description": group.description},
    )
    return group


def update_group(
    db: Session,
    group_id: int,
    payload: GroupUpdate,
    *,
    actor: User | None = None,
) -> Group | None:
    group = db.get(Group, group_id)
    if not group:
        return None
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise ValueError("Group name is required")
        existing = db.scalar(select(Group).where(Group.name == name, Group.id != group_id))
        if existing:
            raise ValueError("Group name already exists")
        group.name = name
    if payload.description is not None:
        group.description = payload.description
    db.add(group)
    db.commit()
    db.refresh(group)
    write_audit_log(
        db,
        actor=actor,
        action="group.updated",
        target_type="group",
        target_id=group.id,
        group_id=group.id,
        detail={"name": group.name, "description": group.description},
    )
    return group


def delete_group(db: Session, group_id: int, *, actor: User | None = None) -> bool:
    group = db.get(Group, group_id)
    if not group:
        return False
    detail = {"name": group.name, "description": group.description}
    db.delete(group)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="group.deleted",
        target_type="group",
        target_id=group_id,
        group_id=group_id,
        detail=detail,
    )
    return True


def list_group_members(db: Session, group_id: int) -> list[UserGroup]:
    return list(
        db.scalars(
            select(UserGroup)
            .options(selectinload(UserGroup.user), selectinload(UserGroup.group))
            .where(UserGroup.group_id == group_id)
            .order_by(UserGroup.id.desc())
        )
    )


def add_group_member(
    db: Session,
    group_id: int,
    user_id: int,
    *,
    actor: User | None = None,
) -> UserGroup:
    group = db.get(Group, group_id)
    if not group:
        raise ValueError("Group not found")
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    membership = db.scalar(
        select(UserGroup).where(UserGroup.group_id == group_id, UserGroup.user_id == user_id)
    )
    if membership:
        membership.group = group
        membership.user = user
        return membership
    membership = UserGroup(group_id=group_id, user_id=user_id)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    membership.group = group
    membership.user = user
    write_audit_log(
        db,
        actor=actor,
        action="group.member.added",
        target_type="user_group",
        target_id=membership.id,
        user_id=user.id,
        group_id=group.id,
        detail={"username": user.username, "group_name": group.name},
    )
    return membership


def remove_group_member(
    db: Session,
    group_id: int,
    user_id: int,
    *,
    actor: User | None = None,
) -> bool:
    membership = db.scalar(
        select(UserGroup).where(UserGroup.group_id == group_id, UserGroup.user_id == user_id)
    )
    if not membership:
        return False
    membership_id = membership.id
    db.delete(membership)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="group.member.removed",
        target_type="user_group",
        target_id=membership_id,
        user_id=user_id,
        group_id=group_id,
    )
    return True


def list_document_group_permissions(db: Session, document_id: int) -> list[GroupPermission]:
    return list(
        db.scalars(
            select(GroupPermission)
            .options(selectinload(GroupPermission.group))
            .where(GroupPermission.document_id == document_id)
            .order_by(GroupPermission.id.desc())
        )
    )


def upsert_group_permission(
    db: Session,
    payload: GroupPermissionCreate,
    *,
    actor: User | None = None,
) -> GroupPermission:
    document = db.get(Document, payload.document_id)
    if not document:
        raise ValueError("Document not found")
    group = db.get(Group, payload.group_id)
    if not group:
        raise ValueError("Group not found")
    permission = db.scalar(
        select(GroupPermission).where(
            GroupPermission.document_id == payload.document_id,
            GroupPermission.group_id == payload.group_id,
        )
    )
    if permission:
        permission.can_read = payload.can_read
        permission.can_write = payload.can_write
        action = "permission.group.updated"
    else:
        permission = GroupPermission(**payload.model_dump())
        db.add(permission)
        action = "permission.group.created"
    db.commit()
    db.refresh(permission)
    permission.group = group
    write_audit_log(
        db,
        actor=actor,
        action=action,
        target_type="group_permission",
        target_id=permission.id,
        document_id=permission.document_id,
        group_id=permission.group_id,
        detail={
            "can_read": permission.can_read,
            "can_write": permission.can_write,
            "group_name": group.name,
            "document_filename": document.filename,
        },
    )
    return permission


def delete_group_permission(
    db: Session,
    permission_id: int,
    *,
    actor: User | None = None,
) -> bool:
    permission = db.get(GroupPermission, permission_id)
    if not permission:
        return False
    document_id = permission.document_id
    group_id = permission.group_id
    detail = {"can_read": permission.can_read, "can_write": permission.can_write}
    db.delete(permission)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="permission.group.deleted",
        target_type="group_permission",
        target_id=permission_id,
        document_id=document_id,
        group_id=group_id,
        detail=detail,
    )
    return True


def list_audit_logs(db: Session, limit: int = 100) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))


def write_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    document_id: int | None = None,
    user_id: int | None = None,
    group_id: int | None = None,
    detail: dict | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        document_id=document_id,
        user_id=user_id,
        group_id=group_id,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
    )
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log
