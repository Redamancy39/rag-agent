from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCollectionCreate(BaseModel):
    name: str
    description: str | None = None


class DocumentCollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DocumentCollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    owner_id: int
    owner_username: str | None = None
    document_count: int = 0
    can_read: bool = False
    can_write: bool = False
    created_at: datetime
    updated_at: datetime | None


class CollectionUserPermissionCreate(BaseModel):
    user_id: int
    can_read: bool = True
    can_write: bool = False


class CollectionUserPermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    collection_id: int
    user_id: int
    user_username: str | None = None
    can_read: bool
    can_write: bool
    created_at: datetime


class CollectionGroupPermissionCreate(BaseModel):
    group_id: int
    can_read: bool = True
    can_write: bool = False


class CollectionGroupPermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    collection_id: int
    group_id: int
    group_name: str | None = None
    can_read: bool
    can_write: bool
    created_at: datetime


class DocumentCollectionMoveRequest(BaseModel):
    document_ids: list[int]
    collection_id: int | None = None


class DocumentCollectionMoveResult(BaseModel):
    moved_count: int
    document_ids: list[int]
    collection_id: int | None
