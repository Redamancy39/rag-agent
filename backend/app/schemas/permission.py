from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PermissionCreate(BaseModel):
    document_id: int
    user_id: int
    can_read: bool = True
    can_write: bool = False


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    user_id: int
    user_username: str | None = None
    can_read: bool
    can_write: bool
    created_at: datetime


class GroupCreate(BaseModel):
    name: str
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class UserGroupCreate(BaseModel):
    user_id: int


class UserGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    user_id: int
    group_name: str | None = None
    user_username: str | None = None
    created_at: datetime


class GroupPermissionCreate(BaseModel):
    document_id: int
    group_id: int
    can_read: bool = True
    can_write: bool = False


class GroupPermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    group_id: int
    group_name: str | None = None
    can_read: bool
    can_write: bool
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    action: str
    target_type: str
    target_id: int | None
    document_id: int | None
    user_id: int | None
    group_id: int | None
    collection_id: int | None
    detail_json: str | None
    created_at: datetime
