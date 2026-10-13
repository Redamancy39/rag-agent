import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addGroupMember, createDocumentCollection, createGroup, deleteCollectionGroupPermission,
  deleteCollectionUserPermission, deleteDocumentCollection, deleteGroup, deleteGroupPermission,
  deletePermission, listAuditLogs, listCollectionGroupPermissions, listCollectionUserPermissions,
  listDocumentCollections, listDocumentGroupPermissions, listDocumentPermissions, listDocuments,
  listGroupMembers, listGroups, listUsers, moveDocumentsToCollection, removeGroupMember,
  upsertCollectionGroupPermission, upsertCollectionUserPermission, upsertDocumentGroupPermission,
  upsertDocumentPermission
} from '../api/client'
import { currentUser, token } from '../auth/session'
import type { DocumentCollectionRead, DocumentRead, GroupRead, UserGroupRead } from '../types'
import {
  documentCollectionForm, groupForm, groupMemberForm, groupPermissionForm, groups, loadingAuditLogs,
  loadingGroups, loadingPermissions, permissionDialogVisible, permissionForm, selectedCollectionGroupPermissions,
  selectedCollectionUserPermissions, selectedGroup, selectedGroupMembers, selectedGroupPermissions,
  selectedPermissionDocument, selectedPermissions, users, auditLogs, collectionGroupPermissionForm,
  collectionPermissionDialogVisible, collectionUserPermissionForm, refreshAuditLogs
} from './permissionAdmin'
import {
  documentCollections, documents, loadingDocumentCollections, loadingDocuments, moveTargetCollectionId,
  refreshDocumentCollections, refreshDocuments, selectedCollection, selectedDocumentRows
} from './documents'

export async function openPermissions(document: DocumentRead) {
  if (!token.value || !currentUser.value?.is_admin) return
  selectedPermissionDocument.value = document
  selectedPermissions.value = []
  selectedGroupPermissions.value = []
  permissionForm.user_id = null
  permissionForm.can_read = true
  permissionForm.can_write = false
  groupPermissionForm.group_id = null
  groupPermissionForm.can_read = true
  groupPermissionForm.can_write = false
  permissionDialogVisible.value = true
  loadingPermissions.value = true
  try {
    const [userList, groupList, permissions, groupPermissions] = await Promise.all([
      listUsers(token.value),
      listGroups(token.value),
      listDocumentPermissions(token.value, document.id),
      listDocumentGroupPermissions(token.value, document.id)
    ])
    users.value = userList
    groups.value = groupList
    selectedPermissions.value = permissions
    selectedGroupPermissions.value = groupPermissions
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限信息加载失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function grantDocumentUser(userId: number, canRead: boolean, canWrite: boolean) {
  if (!token.value || !selectedPermissionDocument.value || !userId) {
    ElMessage.warning('请选择要授权的用户')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertDocumentPermission(token.value, {
      document_id: selectedPermissionDocument.value.id,
      user_id: userId,
      can_read: canRead,
      can_write: canWrite
    })
    selectedPermissions.value = await listDocumentPermissions(
      token.value,
      selectedPermissionDocument.value.id
    )
    ElMessage.success('权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function grantDocumentGroup(groupId: number, canRead: boolean, canWrite: boolean) {
  if (!token.value || !selectedPermissionDocument.value || !groupId) {
    ElMessage.warning('请选择要授权的用户组/部门')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertDocumentGroupPermission(token.value, {
      document_id: selectedPermissionDocument.value.id,
      group_id: groupId,
      can_read: canRead,
      can_write: canWrite
    })
    selectedGroupPermissions.value = await listDocumentGroupPermissions(
      token.value,
      selectedPermissionDocument.value.id
    )
    ElMessage.success('组权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '组权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function revokePermission(permission: { id: number }) {
  if (!token.value || !selectedPermissionDocument.value) return
  loadingPermissions.value = true
  try {
    await deletePermission(token.value, permission.id)
    selectedPermissions.value = selectedPermissions.value.filter((item) => item.id !== permission.id)
    ElMessage.success('权限已撤销')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限撤销失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function revokeGroupPermission(permission: { id: number }) {
  if (!token.value) return
  loadingPermissions.value = true
  try {
    await deleteGroupPermission(token.value, permission.id)
    selectedGroupPermissions.value = selectedGroupPermissions.value.filter(
      (item) => item.id !== permission.id
    )
    ElMessage.success('组权限已撤销')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '组权限撤销失败')
  } finally {
    loadingPermissions.value = false
  }
}

export function handleDocumentSelectionChange(rows: DocumentRead[]) {
  selectedDocumentRows.value = rows
}

export async function moveSelectedDocuments() {
  if (!token.value || !currentUser.value?.is_admin) return
  if (!selectedDocumentRows.value.length) {
    ElMessage.warning('请先选择要移动的文档')
    return
  }
  if (moveTargetCollectionId.value === null) {
    ElMessage.warning('请选择目标文档集')
    return
  }
  const collectionId =
    moveTargetCollectionId.value === 'unassigned'
      ? null
      : moveTargetCollectionId.value
  const targetName =
    collectionId === null
      ? '未分组'
      : documentCollections.value.find((item) => item.id === collectionId)?.name || '目标文档集'
  try {
    await ElMessageBox.confirm(
      `确定将选中的 ${selectedDocumentRows.value.length} 个文档移动到「${targetName}」吗？移动后访问权限会立即按新文档集重新计算。`,
      '批量移动文档',
      {
        confirmButtonText: '移动',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  loadingDocuments.value = true
  try {
    const result = await moveDocumentsToCollection(
      token.value,
      selectedDocumentRows.value.map((item) => item.id),
      collectionId
    )
    selectedDocumentRows.value = []
    moveTargetCollectionId.value = null
    await Promise.all([refreshDocuments(), refreshDocumentCollections(), refreshAuditLogs()])
    ElMessage.success(`已移动 ${result.moved_count} 个文档`)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '移动文档失败')
  } finally {
    loadingDocuments.value = false
  }
}

export async function submitDocumentCollection() {
  if (!token.value || !documentCollectionForm.name.trim()) {
    ElMessage.warning('请填写文档集名称')
    return
  }
  loadingDocumentCollections.value = true
  try {
    const collection = await createDocumentCollection(token.value, {
      name: documentCollectionForm.name.trim(),
      description: documentCollectionForm.description.trim() || undefined
    })
    documentCollectionForm.name = ''
    documentCollectionForm.description = ''
    await Promise.all([refreshDocumentCollections(), refreshAuditLogs()])
    selectedCollection.value = collection
    ElMessage.success('文档集已创建')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建文档集失败')
  } finally {
    loadingDocumentCollections.value = false
  }
}

export async function removeDocumentCollection(collection: DocumentCollectionRead) {
  if (!token.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除文档集「${collection.name}」吗？其中 ${collection.document_count} 个文档会移至“未分组”，原文件和向量不会删除。`,
      '删除文档集',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  loadingDocumentCollections.value = true
  try {
    await deleteDocumentCollection(token.value, collection.id)
    if (selectedCollection.value?.id === collection.id) {
      selectedCollection.value = null
      selectedCollectionUserPermissions.value = []
      selectedCollectionGroupPermissions.value = []
    }
    await Promise.all([refreshDocumentCollections(), refreshDocuments(), refreshAuditLogs()])
    ElMessage.success('文档集已删除，文档已移至未分组')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除文档集失败')
  } finally {
    loadingDocumentCollections.value = false
  }
}

export async function openCollectionPermissions(collection: DocumentCollectionRead) {
  if (!token.value || !currentUser.value?.is_admin) return
  selectedCollection.value = collection
  selectedCollectionUserPermissions.value = []
  selectedCollectionGroupPermissions.value = []
  collectionUserPermissionForm.user_id = null
  collectionUserPermissionForm.can_read = true
  collectionUserPermissionForm.can_write = false
  collectionGroupPermissionForm.group_id = null
  collectionGroupPermissionForm.can_read = true
  collectionGroupPermissionForm.can_write = false
  collectionPermissionDialogVisible.value = true
  loadingPermissions.value = true
  try {
    const [userList, groupList, userPermissions, groupPermissions] = await Promise.all([
      listUsers(token.value),
      listGroups(token.value),
      listCollectionUserPermissions(token.value, collection.id),
      listCollectionGroupPermissions(token.value, collection.id)
    ])
    users.value = userList
    groups.value = groupList
    selectedCollectionUserPermissions.value = userPermissions
    selectedCollectionGroupPermissions.value = groupPermissions
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文档集权限加载失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function grantCollectionUser(userId: number, canRead: boolean, canWrite: boolean) {
  if (!token.value || !selectedCollection.value || !userId) {
    ElMessage.warning('请选择要授权的用户')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertCollectionUserPermission(token.value, selectedCollection.value.id, {
      user_id: userId,
      can_read: canRead,
      can_write: canWrite
    })
    selectedCollectionUserPermissions.value = await listCollectionUserPermissions(
      token.value,
      selectedCollection.value.id
    )
    await refreshAuditLogs()
    ElMessage.success('文档集用户权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文档集用户权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function grantCollectionGroup(groupId: number, canRead: boolean, canWrite: boolean) {
  if (!token.value || !selectedCollection.value || !groupId) {
    ElMessage.warning('请选择要授权的部门')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertCollectionGroupPermission(token.value, selectedCollection.value.id, {
      group_id: groupId,
      can_read: canRead,
      can_write: canWrite
    })
    selectedCollectionGroupPermissions.value = await listCollectionGroupPermissions(
      token.value,
      selectedCollection.value.id
    )
    await refreshAuditLogs()
    ElMessage.success('文档集部门权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文档集部门权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function revokeCollectionUserPermission(permission: { id: number }) {
  if (!token.value) return
  loadingPermissions.value = true
  try {
    await deleteCollectionUserPermission(token.value, permission.id)
    selectedCollectionUserPermissions.value =
      selectedCollectionUserPermissions.value.filter((item) => item.id !== permission.id)
    await refreshAuditLogs()
    ElMessage.success('文档集用户权限已撤销')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限撤销失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function revokeCollectionGroupPermission(permission: { id: number }) {
  if (!token.value) return
  loadingPermissions.value = true
  try {
    await deleteCollectionGroupPermission(token.value, permission.id)
    selectedCollectionGroupPermissions.value =
      selectedCollectionGroupPermissions.value.filter((item) => item.id !== permission.id)
    await refreshAuditLogs()
    ElMessage.success('文档集部门权限已撤销')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限撤销失败')
  } finally {
    loadingPermissions.value = false
  }
}

export async function loadPermissionAdminData() {
  if (!token.value || !currentUser.value?.is_admin) return
  loadingGroups.value = true
  loadingAuditLogs.value = true
  loadingDocuments.value = true
  const selectedGroupId = selectedGroup.value?.id
  try {
    const [userList, groupList, collectionList, logs, documentList] = await Promise.all([
      listUsers(token.value),
      listGroups(token.value),
      listDocumentCollections(token.value),
      listAuditLogs(token.value, 100),
      listDocuments(token.value)
    ])
    users.value = userList
    groups.value = groupList
    documentCollections.value = collectionList
    auditLogs.value = logs
    documents.value = documentList
    if (selectedGroupId) {
      selectedGroup.value = groupList.find((group) => group.id === selectedGroupId) || null
      selectedGroupMembers.value = selectedGroup.value
        ? await listGroupMembers(token.value, selectedGroup.value.id)
        : []
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限管理数据加载失败')
  } finally {
    loadingGroups.value = false
    loadingAuditLogs.value = false
    loadingDocuments.value = false
  }
}

export async function submitGroup() {
  if (!token.value || !groupForm.name.trim()) {
    ElMessage.warning('请填写用户组/部门名称')
    return
  }
  loadingGroups.value = true
  try {
    const group = await createGroup(token.value, {
      name: groupForm.name.trim(),
      description: groupForm.description.trim() || undefined
    })
    groups.value.unshift(group)
    selectedGroup.value = group
    selectedGroupMembers.value = []
    groupForm.name = ''
    groupForm.description = ''
    await refreshAuditLogs()
    ElMessage.success('用户组/部门已创建')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '创建用户组失败')
  } finally {
    loadingGroups.value = false
  }
}

export async function selectGroup(group: GroupRead) {
  if (!token.value) return
  selectedGroup.value = group
  selectedGroupMembers.value = []
  groupMemberForm.user_id = null
  loadingGroups.value = true
  try {
    selectedGroupMembers.value = await listGroupMembers(token.value, group.id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '组成员加载失败')
  } finally {
    loadingGroups.value = false
  }
}

export async function submitGroupMember() {
  if (!token.value || !selectedGroup.value || !groupMemberForm.user_id) {
    ElMessage.warning('请选择用户组和用户')
    return
  }
  loadingGroups.value = true
  try {
    await addGroupMember(token.value, selectedGroup.value.id, groupMemberForm.user_id)
    selectedGroupMembers.value = await listGroupMembers(token.value, selectedGroup.value.id)
    groupMemberForm.user_id = null
    await refreshAuditLogs()
    ElMessage.success('成员已加入')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '添加成员失败')
  } finally {
    loadingGroups.value = false
  }
}

export async function removeSelectedGroupMember(member: UserGroupRead) {
  if (!token.value || !selectedGroup.value) return
  loadingGroups.value = true
  try {
    await removeGroupMember(token.value, selectedGroup.value.id, member.user_id)
    selectedGroupMembers.value = selectedGroupMembers.value.filter((item) => item.id !== member.id)
    await refreshAuditLogs()
    ElMessage.success('成员已移除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '移除成员失败')
  } finally {
    loadingGroups.value = false
  }
}

export async function removeGroup(group: GroupRead) {
  if (!token.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除用户组/部门「${group.name}」吗？相关成员和组权限也会删除。`,
      '删除用户组',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  loadingGroups.value = true
  try {
    await deleteGroup(token.value, group.id)
    groups.value = groups.value.filter((item) => item.id !== group.id)
    if (selectedGroup.value?.id === group.id) {
      selectedGroup.value = null
      selectedGroupMembers.value = []
    }
    await refreshAuditLogs()
    ElMessage.success('用户组已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除用户组失败')
  } finally {
    loadingGroups.value = false
  }
}
