import type {
  AuditLogRead,
  ChatJobRead,
  ChatResponse,
  ChatLogRead,
  CollectionGroupPermissionRead,
  CollectionUserPermissionRead,
  DocumentChunkRead,
  DocumentCollectionRead,
  DocumentProcessingJobRead,
  DocumentQualityReportRead,
  DocumentRead,
  GroupPermissionRead,
  GroupRead,
  PermissionRead,
  TokenResponse,
  UserGroupRead,
  UserRead
} from '../types'

export const AUTH_ERROR_EVENT = 'rag-agent-auth-error'

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const API_V1 = `${API_BASE_URL}/api/v1`

export function getApiBaseUrl(): string {
  return API_BASE_URL
}

export async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`)
    return response.ok
  } catch {
    return false
  }
}

export async function registerUser(payload: {
  username: string
  email?: string
  password: string
}): Promise<UserRead> {
  return request<UserRead>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function loginUser(payload: {
  username: string
  password: string
}): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function getCurrentUser(token: string): Promise<UserRead> {
  return request<UserRead>('/auth/me', { token })
}

export async function listUsers(token: string): Promise<UserRead[]> {
  return request<UserRead[]>('/users/', { token })
}

export async function listDocuments(token: string): Promise<DocumentRead[]> {
  return request<DocumentRead[]>('/documents/', { token })
}

export async function listDocumentCollections(
  token: string
): Promise<DocumentCollectionRead[]> {
  return request<DocumentCollectionRead[]>('/document-collections/', { token })
}

export async function createDocumentCollection(
  token: string,
  payload: { name: string; description?: string }
): Promise<DocumentCollectionRead> {
  return request<DocumentCollectionRead>('/document-collections/', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function deleteDocumentCollection(
  token: string,
  collectionId: number
): Promise<void> {
  await request<void>(`/document-collections/${collectionId}`, {
    method: 'DELETE',
    token
  })
}

export async function moveDocumentsToCollection(
  token: string,
  documentIds: number[],
  collectionId: number | null
): Promise<{ moved_count: number; document_ids: number[]; collection_id: number | null }> {
  return request('/document-collections/move-documents', {
    method: 'POST',
    token,
    body: JSON.stringify({
      document_ids: documentIds,
      collection_id: collectionId
    })
  })
}

export async function listCollectionUserPermissions(
  token: string,
  collectionId: number
): Promise<CollectionUserPermissionRead[]> {
  return request<CollectionUserPermissionRead[]>(
    `/document-collections/${collectionId}/user-permissions`,
    { token }
  )
}

export async function upsertCollectionUserPermission(
  token: string,
  collectionId: number,
  payload: { user_id: number; can_read: boolean; can_write: boolean }
): Promise<CollectionUserPermissionRead> {
  return request<CollectionUserPermissionRead>(
    `/document-collections/${collectionId}/user-permissions`,
    {
      method: 'POST',
      token,
      body: JSON.stringify(payload)
    }
  )
}

export async function deleteCollectionUserPermission(
  token: string,
  permissionId: number
): Promise<void> {
  await request<void>(`/document-collections/user-permissions/${permissionId}`, {
    method: 'DELETE',
    token
  })
}

export async function listCollectionGroupPermissions(
  token: string,
  collectionId: number
): Promise<CollectionGroupPermissionRead[]> {
  return request<CollectionGroupPermissionRead[]>(
    `/document-collections/${collectionId}/group-permissions`,
    { token }
  )
}

export async function upsertCollectionGroupPermission(
  token: string,
  collectionId: number,
  payload: { group_id: number; can_read: boolean; can_write: boolean }
): Promise<CollectionGroupPermissionRead> {
  return request<CollectionGroupPermissionRead>(
    `/document-collections/${collectionId}/group-permissions`,
    {
      method: 'POST',
      token,
      body: JSON.stringify(payload)
    }
  )
}

export async function deleteCollectionGroupPermission(
  token: string,
  permissionId: number
): Promise<void> {
  await request<void>(`/document-collections/group-permissions/${permissionId}`, {
    method: 'DELETE',
    token
  })
}

export async function getDocument(token: string, documentId: number): Promise<DocumentRead> {
  return request<DocumentRead>(`/documents/${documentId}`, { token })
}

export async function listDocumentChunks(
  token: string,
  documentId: number,
  limit = 100
): Promise<DocumentChunkRead[]> {
  return request<DocumentChunkRead[]>(`/documents/${documentId}/chunks?limit=${limit}`, { token })
}

export async function listDocumentJobs(
  token: string,
  documentId: number
): Promise<DocumentProcessingJobRead[]> {
  return request<DocumentProcessingJobRead[]>(`/documents/${documentId}/jobs`, { token })
}

export async function getDocumentQualityReport(
  token: string,
  documentId: number
): Promise<DocumentQualityReportRead> {
  return request<DocumentQualityReportRead>(`/documents/${documentId}/quality-report`, { token })
}

export async function deleteDocument(token: string, documentId: number): Promise<void> {
  await request<void>(`/documents/${documentId}`, {
    method: 'DELETE',
    token
  })
}

export async function normalizeDocumentChunks(
  token: string,
  documentId: number
): Promise<DocumentRead> {
  return request<DocumentRead>(`/documents/${documentId}/normalize-chunks`, {
    method: 'POST',
    token
  })
}

export async function listDocumentPermissions(
  token: string,
  documentId: number
): Promise<PermissionRead[]> {
  return request<PermissionRead[]>(`/permissions/documents/${documentId}`, { token })
}

export async function listGroups(token: string): Promise<GroupRead[]> {
  return request<GroupRead[]>('/permissions/groups', { token })
}

export async function createGroup(
  token: string,
  payload: { name: string; description?: string }
): Promise<GroupRead> {
  return request<GroupRead>('/permissions/groups', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function deleteGroup(token: string, groupId: number): Promise<void> {
  await request<void>(`/permissions/groups/${groupId}`, {
    method: 'DELETE',
    token
  })
}

export async function listGroupMembers(token: string, groupId: number): Promise<UserGroupRead[]> {
  return request<UserGroupRead[]>(`/permissions/groups/${groupId}/members`, { token })
}

export async function addGroupMember(
  token: string,
  groupId: number,
  userId: number
): Promise<UserGroupRead> {
  return request<UserGroupRead>(`/permissions/groups/${groupId}/members`, {
    method: 'POST',
    token,
    body: JSON.stringify({ user_id: userId })
  })
}

export async function removeGroupMember(
  token: string,
  groupId: number,
  userId: number
): Promise<void> {
  await request<void>(`/permissions/groups/${groupId}/members/${userId}`, {
    method: 'DELETE',
    token
  })
}

export async function listDocumentGroupPermissions(
  token: string,
  documentId: number
): Promise<GroupPermissionRead[]> {
  return request<GroupPermissionRead[]>(
    `/permissions/documents/${documentId}/group-permissions`,
    { token }
  )
}

export async function upsertDocumentPermission(
  token: string,
  payload: {
    document_id: number
    user_id: number
    can_read: boolean
    can_write: boolean
  }
): Promise<PermissionRead> {
  return request<PermissionRead>('/permissions/', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function deletePermission(token: string, permissionId: number): Promise<void> {
  await request<void>(`/permissions/${permissionId}`, {
    method: 'DELETE',
    token
  })
}

export async function upsertDocumentGroupPermission(
  token: string,
  payload: {
    document_id: number
    group_id: number
    can_read: boolean
    can_write: boolean
  }
): Promise<GroupPermissionRead> {
  return request<GroupPermissionRead>('/permissions/group-permissions', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function deleteGroupPermission(token: string, permissionId: number): Promise<void> {
  await request<void>(`/permissions/group-permissions/${permissionId}`, {
    method: 'DELETE',
    token
  })
}

export async function listAuditLogs(token: string, limit = 100): Promise<AuditLogRead[]> {
  return request<AuditLogRead[]>(`/permissions/audit-logs?limit=${limit}`, { token })
}

export async function askQuestion(
  token: string,
  payload: {
    question: string
    document_ids?: number[]
    top_k?: number
  }
): Promise<ChatResponse> {
  return request<ChatResponse>('/chat/', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function createChatJob(
  token: string,
  payload: {
    question: string
    document_ids?: number[]
    top_k?: number
  }
): Promise<ChatJobRead> {
  return request<ChatJobRead>('/chat/jobs', {
    method: 'POST',
    token,
    body: JSON.stringify(payload)
  })
}

export async function getChatJob(token: string, jobId: number): Promise<ChatJobRead> {
  return request<ChatJobRead>(`/chat/jobs/${jobId}`, { token })
}

export async function listChatHistory(token: string, limit = 50): Promise<ChatLogRead[]> {
  return request<ChatLogRead[]>(`/chat/history?limit=${limit}`, { token })
}

export async function deleteChatLog(token: string, logId: number): Promise<void> {
  await request<void>(`/chat/history/${logId}`, {
    method: 'DELETE',
    token
  })
}

export function uploadDocument(
  token: string,
  file: File,
  llmChunkNormalizationMode: 'auto' | 'enabled' | 'disabled',
  collectionId: number | null,
  onProgress: (percent: number) => void
): Promise<DocumentRead> {
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('llm_chunk_normalization_mode', llmChunkNormalizationMode)
    if (collectionId !== null) {
      formData.append('collection_id', String(collectionId))
    }

    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_V1}/documents/upload`)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      const parsed = parseJson(xhr.responseText)
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as DocumentRead)
        return
      }
      const message = getErrorMessage(parsed, `上传失败，HTTP ${xhr.status}`)
      if (xhr.status === 401) {
        emitAuthError(message)
      }
      reject(new ApiError(message, xhr.status, parsed))
    }

    xhr.onerror = () => reject(new Error('网络请求失败，请检查后端服务是否启动'))
    xhr.send(formData)
  })
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const headers = new Headers(options.headers)
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (options.token) {
    headers.set('Authorization', `Bearer ${options.token}`)
  }

  const response = await fetch(`${API_V1}${path}`, {
    ...options,
    headers
  })
  const parsed = parseJson(await response.text())
  if (!response.ok) {
    const message = getErrorMessage(parsed, `请求失败，HTTP ${response.status}`)
    if (response.status === 401) {
      emitAuthError(message)
    }
    throw new ApiError(message, response.status, parsed)
  }
  return parsed as T
}

function emitAuthError(message: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem('rag_agent_token')
  window.dispatchEvent(
    new CustomEvent(AUTH_ERROR_EVENT, {
      detail: { message }
    })
  )
}

function parseJson(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    return JSON.stringify(detail)
  }
  if (typeof payload === 'string' && payload) return payload
  return fallback
}
