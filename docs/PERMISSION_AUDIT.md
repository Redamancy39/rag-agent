# 文档集、用户组/部门权限与审计日志

当前权限系统已经从“单用户-单文档授权”扩展为“用户组/部门 + 文档集批量授权”。

## 权限生效范围

- 管理员可以访问全部文档，并可以维护用户组、成员、用户授权和部门授权。
- 文档上传者默认拥有自己上传文档的访问权。
- 普通用户可以访问自己上传的文档、被直接授权的文档，以及所在用户组/部门被授权的文档。
- 普通用户还可以访问直接授权给自己的文档集，以及所在部门被授权的文档集。
- 每份文档最多归属一个文档集；文档移动后，集合权限立即生效，但文档上传者仍保留 owner 权限。
- 文档列表、文档详情、切块预览、任务记录、质量报告和 RAG 检索都会走后端权限过滤。
- 权限过滤不依赖前端隐藏按钮，核心判断在后端 `document_service.get_accessible_document` 和 `list_accessible_documents` 中完成。

## 数据表

- `groups`：用户组/部门。
- `user_groups`：用户与用户组/部门的成员关系。
- `group_permissions`：用户组/部门对文档的读写授权。
- `document_collections`：文档集及其创建者。
- `collection_user_permissions`：用户对整个文档集的读写授权。
- `collection_group_permissions`：用户组/部门对整个文档集的读写授权。
- `documents.collection_id`：文档的单一文档集归属，可为空。
- `audit_logs`：权限与用户组变更审计日志。

## 管理接口

所有接口都需要管理员 JWT。

```http
GET /api/v1/permissions/groups
POST /api/v1/permissions/groups
PUT /api/v1/permissions/groups/{group_id}
DELETE /api/v1/permissions/groups/{group_id}
```

```http
GET /api/v1/permissions/groups/{group_id}/members
POST /api/v1/permissions/groups/{group_id}/members
DELETE /api/v1/permissions/groups/{group_id}/members/{user_id}
```

```http
GET /api/v1/permissions/documents/{document_id}/group-permissions
POST /api/v1/permissions/group-permissions
DELETE /api/v1/permissions/group-permissions/{permission_id}
```

```http
GET /api/v1/permissions/audit-logs?limit=100
```

```http
GET /api/v1/document-collections/
POST /api/v1/document-collections/
PUT /api/v1/document-collections/{collection_id}
DELETE /api/v1/document-collections/{collection_id}
POST /api/v1/document-collections/move-documents
GET /api/v1/document-collections/{collection_id}/user-permissions
POST /api/v1/document-collections/{collection_id}/user-permissions
GET /api/v1/document-collections/{collection_id}/group-permissions
POST /api/v1/document-collections/{collection_id}/group-permissions
```

## 前端入口

- `文档上传`：选择具有写权限的目标文档集，不选择则进入“未分组”。
- `文档列表`：管理员多选文档并批量移动到目标文档集。
- `系统配置`：管理员可以创建文档集并按用户或部门授权，也可以维护用户组/部门和查看权限审计日志。
- `文档列表 -> 权限`：管理员可以按单个用户授权，也可以按用户组/部门批量授权。

## 建议测试流程

1. 用管理员账号登录。
2. 在系统配置中创建一个文档集，例如“食品安全国标”。
3. 创建一个部门“法规部”，并把普通用户加入该部门。
4. 给“法规部”授予该文档集的可读权限。
5. 在文档列表选择多个文档，批量移动到“食品安全国标”。
6. 退出管理员账号，用普通用户登录。
7. 确认该用户能看到集合内全部文档，并且问答测试只能检索自己有权限的文档。
8. 回到管理员账号查看审计日志，确认文档集创建、文档移动和集合授权都有记录。
