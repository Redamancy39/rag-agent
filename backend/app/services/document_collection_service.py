from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_collection import (
    CollectionGroupPermission,
    CollectionUserPermission,
    DocumentCollection,
)
from app.models.group import Group, UserGroup
from app.models.user import User
from app.schemas.document_collection import (
    CollectionGroupPermissionCreate,
    CollectionUserPermissionCreate,
    DocumentCollectionCreate,
    DocumentCollectionUpdate,
)
from app.services.permission_service import write_audit_log


def list_accessible_collections(db: Session, user: User) -> list[dict]:
    statement = select(DocumentCollection).options(selectinload(DocumentCollection.owner))
    if not user.is_admin:
        user_group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
        direct_ids = select(CollectionUserPermission.collection_id).where(
            CollectionUserPermission.user_id == user.id,
            CollectionUserPermission.can_read.is_(True),
        )
        group_ids = select(CollectionGroupPermission.collection_id).where(
            CollectionGroupPermission.group_id.in_(user_group_ids),
            CollectionGroupPermission.can_read.is_(True),
        )
        statement = statement.where(
            or_(
                DocumentCollection.owner_id == user.id,
                DocumentCollection.id.in_(direct_ids),
                DocumentCollection.id.in_(group_ids),
            )
        )
    collections = list(db.scalars(statement.order_by(DocumentCollection.name.asc())))
    return [_collection_payload(db, collection, user) for collection in collections]


def get_collection(db: Session, collection_id: int) -> DocumentCollection | None:
    return db.scalar(
        select(DocumentCollection)
        .options(selectinload(DocumentCollection.owner))
        .where(DocumentCollection.id == collection_id)
    )


def can_access_collection(
    db: Session,
    collection: DocumentCollection,
    user: User,
    *,
    write: bool = False,
) -> bool:
    if user.is_admin or collection.owner_id == user.id:
        return True
    permission_flag = (
        CollectionUserPermission.can_write if write else CollectionUserPermission.can_read
    )
    direct = db.scalar(
        select(CollectionUserPermission.id).where(
            CollectionUserPermission.collection_id == collection.id,
            CollectionUserPermission.user_id == user.id,
            permission_flag.is_(True),
        )
    )
    if direct:
        return True
    group_ids = select(UserGroup.group_id).where(UserGroup.user_id == user.id)
    group_flag = (
        CollectionGroupPermission.can_write
        if write
        else CollectionGroupPermission.can_read
    )
    inherited = db.scalar(
        select(CollectionGroupPermission.id).where(
            CollectionGroupPermission.collection_id == collection.id,
            CollectionGroupPermission.group_id.in_(group_ids),
            group_flag.is_(True),
        )
    )
    return inherited is not None


def create_collection(
    db: Session,
    payload: DocumentCollectionCreate,
    *,
    actor: User,
) -> dict:
    name = payload.name.strip()
    if not name:
        raise ValueError("Document collection name is required")
    if db.scalar(select(DocumentCollection.id).where(DocumentCollection.name == name)):
        raise ValueError("Document collection name already exists")
    collection = DocumentCollection(
        name=name,
        description=(payload.description or "").strip() or None,
        owner_id=actor.id,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    collection.owner = actor
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.created",
        target_type="document_collection",
        target_id=collection.id,
        collection_id=collection.id,
        detail={"name": collection.name, "description": collection.description},
    )
    return _collection_payload(db, collection, actor)


def update_collection(
    db: Session,
    collection_id: int,
    payload: DocumentCollectionUpdate,
    *,
    actor: User,
) -> dict | None:
    collection = get_collection(db, collection_id)
    if not collection:
        return None
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise ValueError("Document collection name is required")
        duplicate = db.scalar(
            select(DocumentCollection.id).where(
                DocumentCollection.name == name,
                DocumentCollection.id != collection_id,
            )
        )
        if duplicate:
            raise ValueError("Document collection name already exists")
        collection.name = name
    if payload.description is not None:
        collection.description = payload.description.strip() or None
    db.add(collection)
    db.commit()
    db.refresh(collection)
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.updated",
        target_type="document_collection",
        target_id=collection.id,
        collection_id=collection.id,
        detail={"name": collection.name, "description": collection.description},
    )
    return _collection_payload(db, collection, actor)


def delete_collection(db: Session, collection_id: int, *, actor: User) -> bool:
    collection = get_collection(db, collection_id)
    if not collection:
        return False
    document_ids = list(
        db.scalars(select(Document.id).where(Document.collection_id == collection_id))
    )
    db.execute(
        update(Document)
        .where(Document.collection_id == collection_id)
        .values(collection_id=None)
    )
    detail = {
        "name": collection.name,
        "unassigned_document_ids": document_ids,
    }
    db.delete(collection)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.deleted",
        target_type="document_collection",
        target_id=collection_id,
        collection_id=collection_id,
        detail=detail,
    )
    return True


def move_documents(
    db: Session,
    document_ids: list[int],
    collection_id: int | None,
    *,
    actor: User,
) -> dict:
    unique_ids = sorted({int(document_id) for document_id in document_ids if document_id > 0})
    if not unique_ids:
        raise ValueError("Select at least one document")
    collection = None
    if collection_id is not None:
        collection = get_collection(db, collection_id)
        if not collection:
            raise ValueError("Document collection not found")
    documents = list(db.scalars(select(Document).where(Document.id.in_(unique_ids))))
    found_ids = {document.id for document in documents}
    missing_ids = sorted(set(unique_ids) - found_ids)
    if missing_ids:
        raise ValueError(f"Documents not found: {missing_ids}")
    previous = {document.id: document.collection_id for document in documents}
    for document in documents:
        document.collection_id = collection_id
        db.add(document)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.documents_moved",
        target_type="document_collection",
        target_id=collection_id,
        collection_id=collection_id,
        detail={
            "document_ids": unique_ids,
            "previous_collection_ids": previous,
            "collection_name": collection.name if collection else None,
        },
    )
    return {
        "moved_count": len(unique_ids),
        "document_ids": unique_ids,
        "collection_id": collection_id,
    }


def list_user_permissions(
    db: Session,
    collection_id: int,
) -> list[CollectionUserPermission]:
    return list(
        db.scalars(
            select(CollectionUserPermission)
            .options(selectinload(CollectionUserPermission.user))
            .where(CollectionUserPermission.collection_id == collection_id)
            .order_by(CollectionUserPermission.id.desc())
        )
    )


def upsert_user_permission(
    db: Session,
    collection_id: int,
    payload: CollectionUserPermissionCreate,
    *,
    actor: User,
) -> CollectionUserPermission:
    collection = get_collection(db, collection_id)
    if not collection:
        raise ValueError("Document collection not found")
    user = db.get(User, payload.user_id)
    if not user:
        raise ValueError("User not found")
    if collection.owner_id == user.id:
        raise ValueError("Document collection owner already has access")
    permission = db.scalar(
        select(CollectionUserPermission).where(
            CollectionUserPermission.collection_id == collection_id,
            CollectionUserPermission.user_id == payload.user_id,
        )
    )
    if permission:
        action = "document_collection.permission.user.updated"
    else:
        permission = CollectionUserPermission(
            collection_id=collection_id,
            user_id=payload.user_id,
        )
        db.add(permission)
        action = "document_collection.permission.user.created"
    permission.can_read = payload.can_read or payload.can_write
    permission.can_write = payload.can_write
    db.commit()
    db.refresh(permission)
    permission.user = user
    write_audit_log(
        db,
        actor=actor,
        action=action,
        target_type="collection_user_permission",
        target_id=permission.id,
        user_id=user.id,
        collection_id=collection_id,
        detail={
            "collection_name": collection.name,
            "username": user.username,
            "can_read": permission.can_read,
            "can_write": permission.can_write,
        },
    )
    return permission


def delete_user_permission(
    db: Session,
    permission_id: int,
    *,
    actor: User,
) -> bool:
    permission = db.get(CollectionUserPermission, permission_id)
    if not permission:
        return False
    detail = {
        "can_read": permission.can_read,
        "can_write": permission.can_write,
    }
    collection_id = permission.collection_id
    user_id = permission.user_id
    db.delete(permission)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.permission.user.deleted",
        target_type="collection_user_permission",
        target_id=permission_id,
        user_id=user_id,
        collection_id=collection_id,
        detail=detail,
    )
    return True


def list_group_permissions(
    db: Session,
    collection_id: int,
) -> list[CollectionGroupPermission]:
    return list(
        db.scalars(
            select(CollectionGroupPermission)
            .options(selectinload(CollectionGroupPermission.group))
            .where(CollectionGroupPermission.collection_id == collection_id)
            .order_by(CollectionGroupPermission.id.desc())
        )
    )


def upsert_group_permission(
    db: Session,
    collection_id: int,
    payload: CollectionGroupPermissionCreate,
    *,
    actor: User,
) -> CollectionGroupPermission:
    collection = get_collection(db, collection_id)
    if not collection:
        raise ValueError("Document collection not found")
    group = db.get(Group, payload.group_id)
    if not group:
        raise ValueError("Group not found")
    permission = db.scalar(
        select(CollectionGroupPermission).where(
            CollectionGroupPermission.collection_id == collection_id,
            CollectionGroupPermission.group_id == payload.group_id,
        )
    )
    if permission:
        action = "document_collection.permission.group.updated"
    else:
        permission = CollectionGroupPermission(
            collection_id=collection_id,
            group_id=payload.group_id,
        )
        db.add(permission)
        action = "document_collection.permission.group.created"
    permission.can_read = payload.can_read or payload.can_write
    permission.can_write = payload.can_write
    db.commit()
    db.refresh(permission)
    permission.group = group
    write_audit_log(
        db,
        actor=actor,
        action=action,
        target_type="collection_group_permission",
        target_id=permission.id,
        group_id=group.id,
        collection_id=collection_id,
        detail={
            "collection_name": collection.name,
            "group_name": group.name,
            "can_read": permission.can_read,
            "can_write": permission.can_write,
        },
    )
    return permission


def delete_group_permission(
    db: Session,
    permission_id: int,
    *,
    actor: User,
) -> bool:
    permission = db.get(CollectionGroupPermission, permission_id)
    if not permission:
        return False
    detail = {
        "can_read": permission.can_read,
        "can_write": permission.can_write,
    }
    collection_id = permission.collection_id
    group_id = permission.group_id
    db.delete(permission)
    db.commit()
    write_audit_log(
        db,
        actor=actor,
        action="document_collection.permission.group.deleted",
        target_type="collection_group_permission",
        target_id=permission_id,
        group_id=group_id,
        collection_id=collection_id,
        detail=detail,
    )
    return True


def _collection_payload(
    db: Session,
    collection: DocumentCollection,
    user: User,
) -> dict:
    document_count = int(
        db.scalar(
            select(func.count(Document.id)).where(
                Document.collection_id == collection.id
            )
        )
        or 0
    )
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "owner_id": collection.owner_id,
        "owner_username": collection.owner_username,
        "document_count": document_count,
        "can_read": can_access_collection(db, collection, user),
        "can_write": can_access_collection(db, collection, user, write=True),
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }
