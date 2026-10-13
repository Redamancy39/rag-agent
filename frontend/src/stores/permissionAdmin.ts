import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAuditLogs } from '../api/client.ts'
import { currentUser, onSessionReset, token } from '../auth/session.ts'
import { selectedCollection } from './documents.ts'
import type {
  AuditLogRead, CollectionGroupPermissionRead, CollectionUserPermissionRead, DocumentRead,
  GroupPermissionRead, GroupRead, PermissionRead, UserGroupRead, UserRead
} from '../types.ts'

export const permissionSection = ref<'resources' | 'groups' | 'audit'>('resources')
export const loadingPermissions = ref(false)
export const loadingGroups = ref(false)
export const loadingAuditLogs = ref(false)
export const permissionDialogVisible = ref(false)
export const collectionPermissionDialogVisible = ref(false)
export const selectedPermissionDocument = ref<DocumentRead | null>(null)
export const selectedCollectionUserPermissions = ref<CollectionUserPermissionRead[]>([])
export const selectedCollectionGroupPermissions = ref<CollectionGroupPermissionRead[]>([])
export const selectedPermissions = ref<PermissionRead[]>([])
export const selectedGroupPermissions = ref<GroupPermissionRead[]>([])
export const users = ref<UserRead[]>([])
export const groups = ref<GroupRead[]>([])
export const selectedGroup = ref<GroupRead | null>(null)
export const selectedGroupMembers = ref<UserGroupRead[]>([])
export const auditLogs = ref<AuditLogRead[]>([])
export const permissionForm = reactive({ user_id: null as number | null, can_read: true, can_write: false })
export const groupPermissionForm = reactive({ group_id: null as number | null, can_read: true, can_write: false })
export const groupForm = reactive({ name: '', description: '' })
export const groupMemberForm = reactive({ user_id: null as number | null })
export const documentCollectionForm = reactive({ name: '', description: '' })
export const collectionUserPermissionForm = reactive({ user_id: null as number | null, can_read: true, can_write: false })
export const collectionGroupPermissionForm = reactive({ group_id: null as number | null, can_read: true, can_write: false })

export const permissionUserOptions = computed(() => {
  const ownerId = selectedPermissionDocument.value?.owner_id
  return users.value.filter((user) => user.id !== ownerId && user.is_active)
})

export const groupMemberOptions = computed(() => {
  const memberIds = new Set(selectedGroupMembers.value.map((member) => member.user_id))
  return users.value.filter((user) => user.is_active && !memberIds.has(user.id))
})

export const collectionPermissionUserOptions = computed(() => {
  const ownerId = selectedCollection.value?.owner_id
  return users.value.filter((user) => user.id !== ownerId && user.is_active)
})

export const permissionDialogTitle = computed(() =>
  selectedPermissionDocument.value ? `权限管理：${selectedPermissionDocument.value.filename}` : '权限管理'
)

export function resetPermissionAdmin() {
  loadingPermissions.value = false
  loadingGroups.value = false
  loadingAuditLogs.value = false
  permissionDialogVisible.value = false
  collectionPermissionDialogVisible.value = false
  selectedPermissionDocument.value = null
  selectedCollectionUserPermissions.value = []
  selectedCollectionGroupPermissions.value = []
  selectedPermissions.value = []
  selectedGroupPermissions.value = []
  users.value = []
  groups.value = []
  selectedGroup.value = null
  selectedGroupMembers.value = []
  auditLogs.value = []
  permissionSection.value = 'resources'
  permissionForm.user_id = null
  groupPermissionForm.group_id = null
  groupForm.name = ''
  groupForm.description = ''
  groupMemberForm.user_id = null
  documentCollectionForm.name = ''
  documentCollectionForm.description = ''
}

onSessionReset(resetPermissionAdmin)

export async function refreshAuditLogs() {
  if (!token.value || !currentUser.value?.is_admin) return
  loadingAuditLogs.value = true
  try {
    auditLogs.value = await listAuditLogs(token.value, 100)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '审计日志加载失败')
  } finally {
    loadingAuditLogs.value = false
  }
}
