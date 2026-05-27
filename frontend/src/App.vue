<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  CircleCheck,
  Cloudy,
  Delete,
  Document,
  Files,
  Key,
  Lock,
  Refresh,
  UploadFilled,
  User,
  View
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadRequestOptions } from 'element-plus'
import {
  addGroupMember,
  askQuestion,
  createGroup,
  deleteChatLog,
  deleteDocument,
  deleteGroup,
  deleteGroupPermission,
  deletePermission,
  getApiBaseUrl,
  getCurrentUser,
  getDocument,
  getDocumentQualityReport,
  healthCheck,
  listChatHistory,
  listDocumentChunks,
  listDocumentGroupPermissions,
  listDocumentJobs,
  listDocumentPermissions,
  listDocuments,
  listAuditLogs,
  listGroupMembers,
  listGroups,
  listUsers,
  loginUser,
  normalizeDocumentChunks,
  removeGroupMember,
  registerUser,
  upsertDocumentGroupPermission,
  upsertDocumentPermission,
  uploadDocument
} from './api/client'
import type {
  AuditLogRead,
  AnswerSections,
  ChatResponse,
  ChatLogRead,
  Citation,
  DocumentChunkRead,
  DocumentProcessingJobRead,
  DocumentQualityReportRead,
  DocumentRead,
  EvidenceRow,
  IngestionTraceItem,
  GroupPermissionRead,
  GroupRead,
  PermissionRead,
  UploadProgressItem,
  UserGroupRead,
  UserRead
} from './types'

type ActiveView = 'upload' | 'documents' | 'chat' | 'settings'

interface ChatTurn {
  id: string
  logId: number | null
  question: string
  documentIds: number[]
  documentNames: string[]
  createdAt: string
  response: ChatResponse | null
  loading: boolean
  error: string | null
  progress: number
  progressMessage: string
}

const token = ref(localStorage.getItem('rag_agent_token') || '')
const currentUser = ref<UserRead | null>(null)
const documents = ref<DocumentRead[]>([])
const uploadItems = ref<UploadProgressItem[]>([])
const authMode = ref<'login' | 'register'>('login')
const activeView = ref<ActiveView>('upload')
const loadingUser = ref(false)
const loadingDocuments = ref(false)
const loadingChunks = ref(false)
const loadingJobs = ref(false)
const loadingQualityReport = ref(false)
const loadingPermissions = ref(false)
const loadingGroups = ref(false)
const loadingAuditLogs = ref(false)
const loadingChat = ref(false)
const loadingChatHistory = ref(false)
const deletingDocumentId = ref<number | null>(null)
const deletingChatLogId = ref<number | null>(null)
const normalizingDocumentId = ref<number | null>(null)
const backendOnline = ref(false)
const chunkDialogVisible = ref(false)
const jobDialogVisible = ref(false)
const qualityDialogVisible = ref(false)
const permissionDialogVisible = ref(false)
const selectedDocument = ref<DocumentRead | null>(null)
const selectedChunks = ref<DocumentChunkRead[]>([])
const selectedJobDocument = ref<DocumentRead | null>(null)
const selectedJobs = ref<DocumentProcessingJobRead[]>([])
const selectedQualityDocument = ref<DocumentRead | null>(null)
const selectedQualityReport = ref<DocumentQualityReportRead | null>(null)
const selectedPermissionDocument = ref<DocumentRead | null>(null)
const selectedPermissions = ref<PermissionRead[]>([])
const selectedGroupPermissions = ref<GroupPermissionRead[]>([])
const users = ref<UserRead[]>([])
const groups = ref<GroupRead[]>([])
const selectedGroup = ref<GroupRead | null>(null)
const selectedGroupMembers = ref<UserGroupRead[]>([])
const auditLogs = ref<AuditLogRead[]>([])
const selectedChatDocumentIds = ref<number[]>([])
const chatQuestion = ref('')
const chatTurns = ref<ChatTurn[]>([])
const chatHistoryItems = ref<ChatTurn[]>([])
const evidenceCollapseNames = ref<string[]>([])
const chatThreadRef = ref<HTMLElement | null>(null)
const enableLlmChunkNormalization = ref(true)

const authForm = reactive({
  username: '',
  email: '',
  password: ''
})

const permissionForm = reactive({
  user_id: null as number | null,
  can_read: true,
  can_write: false
})

const groupPermissionForm = reactive({
  group_id: null as number | null,
  can_read: true,
  can_write: false
})

const groupForm = reactive({
  name: '',
  description: ''
})

const groupMemberForm = reactive({
  user_id: null as number | null
})

const isLoggedIn = computed(() => Boolean(token.value && currentUser.value))
const indexedCount = computed(() => documents.value.filter((item) => item.status === 'indexed').length)
const failedCount = computed(() => documents.value.filter((item) => item.status === 'failed').length)
const indexedDocuments = computed(() => documents.value.filter((item) => item.status === 'indexed'))
const processingCount = computed(() =>
  documents.value.filter((item) => !['indexed', 'failed'].includes(item.status)).length
)
const totalChunkCount = computed(() =>
  documents.value.reduce((total, item) => total + Number(item.chunk_count || 0), 0)
)
const totalFileSize = computed(() =>
  documents.value.reduce((total, item) => total + Number(item.file_size || 0), 0)
)
const demoOverviewCards = computed(() => [
  { label: '可访问文档', value: documents.value.length, note: '按登录用户权限过滤' },
  { label: '已入库文档', value: indexedCount.value, note: '可参与 RAG 检索' },
  { label: '总切块数', value: totalChunkCount.value, note: '含页码与来源 metadata' },
  { label: '处理中', value: processingCount.value, note: '队列 / OCR / LLM / Embedding' }
])
const ragPipelineStages = [
  {
    title: '1. Ingestion Agent 探测',
    detail: '识别文件类型、PDF 可读性、表格密度、OCR 与 LLM 整理需求。'
  },
  {
    title: '2. 解析与预处理',
    detail: '优先 PyMuPDF / 文本层解析，必要时 PaddleOCR fallback，并保留页码。'
  },
  {
    title: '3. 表格与切块质量增强',
    detail: '表格行转事实文本，低质量 OCR / 表格块可由 LLM 归一化。'
  },
  {
    title: '4. 向量化与混合检索',
    detail: 'BGE Embedding 写入 ChromaDB，问答阶段融合向量、BM25、关键词和 Reranker。'
  },
  {
    title: '5. 权限感知问答',
    detail: '后端计算可访问文档范围，证据不足时返回未找到，并记录日志。'
  }
]
const capabilityCards = [
  { title: '权限控制', value: 'JWT + 用户 / 部门权限', status: '已接入' },
  { title: '文档入库', value: 'PDF / Markdown / TXT + OCR fallback', status: '已跑通' },
  { title: '检索增强', value: '向量 + BM25 + 关键词 + Reranker', status: '已接入' },
  { title: 'Agent 化', value: '轻量 Ingestion Agent，LangGraph 预留', status: '演示版' },
  { title: '可观测性', value: '任务表、质量报告、审计日志', status: '已接入' },
  { title: '评测闭环', value: '500 条 v2 测试集，离线重判 90.40%', status: '基线可用' }
]
const chatHistory = computed(() => [...chatHistoryItems.value].reverse())
const pageTitle = computed(() => {
  if (activeView.value === 'documents') return '文档列表'
  if (activeView.value === 'chat') return '问答测试'
  if (activeView.value === 'settings') return '系统配置'
  return '文档上传'
})
const pageSubtitle = computed(() => {
  if (activeView.value === 'documents') {
    return '查看已入库文档、上传者、入库状态、分块数，并支持管理员删除。'
  }
  if (activeView.value === 'chat') {
    return '对话式 RAG 问答，可选择任意数量文档，回答按分类判断、结论、依据、引用输出。'
  }
  if (activeView.value === 'settings') {
    return '当前先做只读展示，后续再接入管理员可编辑配置、权限策略和运行监控。'
  }
  return '登录后上传 PDF / Markdown / TXT，后端自动解析、分块并写入 ChromaDB。'
})
const chunkDialogTitle = computed(() =>
  selectedDocument.value ? `分块预览：${selectedDocument.value.filename}` : '分块预览'
)

const jobDialogTitle = computed(() =>
  selectedJobDocument.value ? `处理任务：${selectedJobDocument.value.filename}` : '处理任务'
)

const qualityDialogTitle = computed(() =>
  selectedQualityDocument.value ? `质量报告：${selectedQualityDocument.value.filename}` : '质量报告'
)

const permissionDialogTitle = computed(() =>
  selectedPermissionDocument.value ? `权限管理：${selectedPermissionDocument.value.filename}` : '权限管理'
)

const permissionUserOptions = computed(() => {
  const ownerId = selectedPermissionDocument.value?.owner_id
  return users.value.filter((user) => user.id !== ownerId && user.is_active)
})

const groupMemberOptions = computed(() => {
  const memberIds = new Set(selectedGroupMembers.value.map((member) => member.user_id))
  return users.value.filter((user) => user.is_active && !memberIds.has(user.id))
})

onMounted(async () => {
  await refreshBackendStatus()
  if (token.value) {
    await loadCurrentUser()
    await refreshDocuments()
    await loadChatHistory()
  }
})

function selectView(view: ActiveView) {
  if (!isLoggedIn.value && view !== 'upload') {
    activeView.value = 'upload'
    ElMessage.warning('请先登录后再使用该功能')
    return
  }
  activeView.value = view
  if (view === 'documents' || view === 'chat') {
    void refreshDocuments()
  }
  if (view === 'settings' && currentUser.value?.is_admin) {
    void loadPermissionAdminData()
  }
}

async function refreshBackendStatus() {
  backendOnline.value = await healthCheck()
}

async function submitAuth() {
  if (!authForm.username || !authForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loadingUser.value = true
  try {
    if (authMode.value === 'register') {
      await registerUser({
        username: authForm.username,
        email: authForm.email || undefined,
        password: authForm.password
      })
      ElMessage.success('注册成功，已自动登录')
    }
    const result = await loginUser({
      username: authForm.username,
      password: authForm.password
    })
    token.value = result.access_token
    localStorage.setItem('rag_agent_token', result.access_token)
    await loadCurrentUser()
    await refreshDocuments()
    await loadChatHistory()
    ElMessage.success('登录成功')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loadingUser.value = false
  }
}

async function loadCurrentUser() {
  if (!token.value) return
  loadingUser.value = true
  try {
    currentUser.value = await getCurrentUser(token.value)
  } catch {
    logout(false)
  } finally {
    loadingUser.value = false
  }
}

async function refreshDocuments() {
  if (!token.value) {
    documents.value = []
    return
  }
  loadingDocuments.value = true
  try {
    documents.value = await listDocuments(token.value)
    syncUploadItemsWithDocuments()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文档列表加载失败')
  } finally {
    loadingDocuments.value = false
  }
}

async function loadChatHistory(options: { hydrateConversation?: boolean } = {}) {
  if (!token.value) {
    chatTurns.value = []
    chatHistoryItems.value = []
    return
  }
  loadingChatHistory.value = true
  try {
    const logs = await listChatHistory(token.value, 50)
    const turns = logs.slice().reverse().map(chatLogToTurn)
    chatHistoryItems.value = turns
    if (options.hydrateConversation === true) {
      chatTurns.value = turns.map(cloneChatTurn)
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '问答历史加载失败')
  } finally {
    loadingChatHistory.value = false
    await scrollChatToBottom()
  }
}

function logout(showMessage = true) {
  token.value = ''
  currentUser.value = null
  documents.value = []
  selectedDocument.value = null
  selectedChunks.value = []
  selectedJobDocument.value = null
  selectedJobs.value = []
  selectedQualityDocument.value = null
  selectedQualityReport.value = null
  selectedPermissionDocument.value = null
  selectedPermissions.value = []
  selectedGroupPermissions.value = []
  groups.value = []
  selectedGroup.value = null
  selectedGroupMembers.value = []
  auditLogs.value = []
  selectedChatDocumentIds.value = []
  chatTurns.value = []
  chatHistoryItems.value = []
  evidenceCollapseNames.value = []
  activeView.value = 'upload'
  localStorage.removeItem('rag_agent_token')
  if (showMessage) {
    ElMessage.success('已退出登录')
  }
}

function removeUploadItem(id: string) {
  uploadItems.value = uploadItems.value.filter((item) => item.id !== id)
}

function syncUploadItemsWithDocuments() {
  const byId = new Map(documents.value.map((document) => [document.id, document]))
  for (const item of uploadItems.value) {
    if (!item.document_id) continue
    const document = byId.get(item.document_id)
    if (!document) continue
    applyDocumentStatusToUploadItem(item, document)
  }
}

function applyDocumentStatusToUploadItem(item: UploadProgressItem, document: DocumentRead) {
  item.progress = statusProgress(document.status)
  item.message = statusMessage(document)
  item.stageLabel = statusLabel(document.status)
  item.progressCurrent = undefined
  item.progressTotal = undefined
  if (document.status === 'indexed') {
    item.status = 'success'
    item.progress = 100
    return
  }
  if (document.status === 'failed') {
    item.status = 'error'
    item.progress = 100
    return
  }
  item.status = 'indexing'
}

async function handleUpload(options: UploadRequestOptions) {
  if (!token.value) {
    ElMessage.warning('请先登录后再上传文档')
    return
  }
  const file = options.file
  const uploadItem: UploadProgressItem = {
    id: `${file.name}-${Date.now()}`,
    filename: file.name,
    progress: 0,
    status: 'uploading',
    message: '正在上传原始文件'
  }
  uploadItems.value.unshift(uploadItem)

  try {
    const document = await uploadDocument(token.value, file, enableLlmChunkNormalization.value, (progress) => {
      uploadItem.progress = Math.min(progress, 12)
      if (progress >= 100) {
        uploadItem.status = 'indexing'
        uploadItem.message = '上传完成，等待后台解析入库'
      }
    })
    uploadItem.document_id = document.id
    uploadItem.progress = statusProgress(document.status)
    uploadItem.status = document.status === 'failed' ? 'error' : 'indexing'
    uploadItem.message = statusMessage(document)
    await refreshDocuments()
    void pollUploadStatus(uploadItem, document.id)
    options.onSuccess?.(document)
  } catch (error) {
    uploadItem.status = 'error'
    uploadItem.message = error instanceof Error ? error.message : '上传失败'
  }
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function statusType(status: string) {
  if (status === 'indexed') return 'success'
  if (status === 'failed') return 'danger'
  if (
    [
      'queued',
      'agent_planning',
      'file_probe',
      'strategy_planner',
      'uploaded',
      'parsing',
      'parse_ocr',
      'preprocessing',
      'ocr',
      'llm_preprocessing_queued',
      'llm_preprocessing',
      'chunking',
      'normalize',
      'chunk_quality',
      'index',
      'embedding',
      'indexing',
      'report'
    ].includes(status)
  ) {
    return 'warning'
  }
  return 'info'
}

function uploadStatusType(status: UploadProgressItem['status']) {
  if (status === 'success') return 'success'
  if (status === 'error') return 'exception'
  return undefined
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: '等待入库',
    agent_planning: 'Agent 规划',
    file_probe: '文件探测',
    strategy_planner: '策略规划',
    uploaded: '已上传',
    parsing: '读取文件',
    parse_ocr: '解析 / OCR',
    preprocessing: '质量检查',
    ocr: 'OCR 识别',
    llm_preprocessing_queued: 'LLM 排队',
    llm_preprocessing: '大模型整理',
    chunking: '正在切块',
    normalize: '归一化整理',
    chunk_quality: '质量评估',
    index: '准备入库',
    embedding: '生成向量',
    indexing: '写入向量库',
    report: '生成报告',
    indexed: '已入库',
    failed: '失败'
  }
  return labels[status] || status
}

function statusMessage(document: DocumentRead) {
  if (document.status_message) return document.status_message
  if (document.status === 'indexed') return `入库完成，共 ${document.chunk_count} 个分块`
  if (document.status === 'failed') return document.error_message || '入库失败'
  return statusLabel(document.status)
}

function jobStatusMessage(job: DocumentProcessingJobRead | null) {
  if (!job) return ''
  if (job.stage === 'llm_preprocessing' && job.progress_detail) {
    return job.progress_detail
  }
  return job.message || ''
}

function jobProgress(job: DocumentProcessingJobRead | null) {
  if (!job) return 0
  if (job.stage !== 'llm_preprocessing' || !job.progress_total) return 0
  return Math.max(0, Math.min(100, Number(job.progress_percent || 0)))
}

function jobProgressMeta(job: DocumentProcessingJobRead | null) {
  if (!job || job.stage !== 'llm_preprocessing' || !job.progress_total) return null
  return {
    stageLabel: statusLabel(job.stage),
    current: Math.max(0, Number(job.progress_current || 0)),
    total: Math.max(0, Number(job.progress_total || 0))
  }
}

function uploadProgressMeta(item: UploadProgressItem) {
  const parts: string[] = []
  if (item.stageLabel) {
    parts.push(`阶段：${item.stageLabel}`)
  }
  if (item.progressTotal) {
    parts.push(`已完成：${item.progressCurrent || 0} / ${item.progressTotal} 个切块`)
  }
  if (item.status === 'indexing' || item.status === 'uploading') {
    parts.push(`进度：${item.progress}%`)
  }
  return parts.join(' · ')
}

function statusProgress(status: string) {
  const values: Record<string, number> = {
    queued: 8,
    agent_planning: 16,
    file_probe: 14,
    strategy_planner: 20,
    uploaded: 12,
    parsing: 24,
    parse_ocr: 30,
    preprocessing: 34,
    ocr: 42,
    llm_preprocessing_queued: 50,
    llm_preprocessing: 56,
    chunking: 68,
    normalize: 62,
    chunk_quality: 72,
    index: 78,
    embedding: 82,
    indexing: 92,
    report: 96,
    indexed: 100,
    failed: 100
  }
  return values[status] ?? 15
}

async function pollUploadStatus(item: UploadProgressItem, documentId: number) {
  if (!token.value) return
  for (let attempt = 0; attempt < 360; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
    if (!token.value) return
    try {
      const document = await getDocument(token.value, documentId)
      const jobs = await listDocumentJobs(token.value, documentId)
      const latestJob = jobs[0] || null
      applyDocumentStatusToUploadItem(item, document)
      const progress = jobProgress(latestJob)
      if (progress > 0 && document.status !== 'indexed' && document.status !== 'failed') {
        item.progress = Math.max(item.progress, progress)
      }
      const meta = jobProgressMeta(latestJob)
      item.stageLabel = meta?.stageLabel || statusLabel(document.status)
      item.progressCurrent = meta?.current
      item.progressTotal = meta?.total
      const detail = jobStatusMessage(latestJob)
      if (detail) {
        item.message = detail
      }
      if (document.status === 'indexed') {
        item.status = 'success'
        item.progress = 100
        await refreshDocuments()
        return
      }
      if (document.status === 'failed') {
        item.status = 'error'
        item.progress = 100
        await refreshDocuments()
        return
      }
      item.status = 'indexing'
      if (attempt % 4 === 0) {
        await refreshDocuments()
      }
    } catch (error) {
      item.status = 'error'
      item.message = error instanceof Error ? error.message : '状态查询失败'
      return
    }
  }
  item.message = '后台入库仍在进行，可以稍后刷新文档列表查看结果'
}

function ownerName(document: DocumentRead) {
  return document.owner_username || `用户 ${document.owner_id}`
}

async function openChunks(document: DocumentRead) {
  if (!token.value) return
  selectedDocument.value = document
  selectedChunks.value = []
  chunkDialogVisible.value = true
  loadingChunks.value = true
  try {
    selectedChunks.value = await listDocumentChunks(token.value, document.id, 50)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分块加载失败')
  } finally {
    loadingChunks.value = false
  }
}

async function openJobs(document: DocumentRead) {
  if (!token.value) return
  selectedJobDocument.value = document
  selectedJobs.value = []
  jobDialogVisible.value = true
  loadingJobs.value = true
  try {
    selectedJobs.value = await listDocumentJobs(token.value, document.id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '处理任务加载失败')
  } finally {
    loadingJobs.value = false
  }
}

async function openQualityReport(document: DocumentRead) {
  if (!token.value) return
  selectedQualityDocument.value = document
  selectedQualityReport.value = null
  qualityDialogVisible.value = true
  loadingQualityReport.value = true
  try {
    selectedQualityReport.value = await getDocumentQualityReport(token.value, document.id)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '质量报告加载失败')
  } finally {
    loadingQualityReport.value = false
  }
}

async function triggerChunkNormalization(document: DocumentRead) {
  if (!token.value) return
  try {
    await ElMessageBox.confirm(
      `确定对「${document.filename}」中低质量 OCR / 表格切块进行 LLM 整理吗？该任务会重写该文档的向量切块。`,
      'LLM 整理',
      {
        confirmButtonText: '开始整理',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }
  normalizingDocumentId.value = document.id
  try {
    const updated = await normalizeDocumentChunks(token.value, document.id)
    documents.value = documents.value.map((item) => (item.id === updated.id ? updated : item))
    ElMessage.success('已加入 LLM 整理队列')
    await refreshDocuments()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'LLM 整理任务提交失败')
  } finally {
    normalizingDocumentId.value = null
  }
}

async function openPermissions(document: DocumentRead) {
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

async function submitPermission() {
  if (!token.value || !selectedPermissionDocument.value || !permissionForm.user_id) {
    ElMessage.warning('请选择要授权的用户')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertDocumentPermission(token.value, {
      document_id: selectedPermissionDocument.value.id,
      user_id: permissionForm.user_id,
      can_read: permissionForm.can_read,
      can_write: permissionForm.can_write
    })
    selectedPermissions.value = await listDocumentPermissions(
      token.value,
      selectedPermissionDocument.value.id
    )
    permissionForm.user_id = null
    permissionForm.can_read = true
    permissionForm.can_write = false
    ElMessage.success('权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

async function submitGroupPermission() {
  if (!token.value || !selectedPermissionDocument.value || !groupPermissionForm.group_id) {
    ElMessage.warning('请选择要授权的用户组/部门')
    return
  }
  loadingPermissions.value = true
  try {
    await upsertDocumentGroupPermission(token.value, {
      document_id: selectedPermissionDocument.value.id,
      group_id: groupPermissionForm.group_id,
      can_read: groupPermissionForm.can_read,
      can_write: groupPermissionForm.can_write
    })
    selectedGroupPermissions.value = await listDocumentGroupPermissions(
      token.value,
      selectedPermissionDocument.value.id
    )
    groupPermissionForm.group_id = null
    groupPermissionForm.can_read = true
    groupPermissionForm.can_write = false
    ElMessage.success('组权限已保存')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '组权限保存失败')
  } finally {
    loadingPermissions.value = false
  }
}

async function revokePermission(permission: PermissionRead) {
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

async function revokeGroupPermission(permission: GroupPermissionRead) {
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

async function loadPermissionAdminData() {
  if (!token.value || !currentUser.value?.is_admin) return
  loadingGroups.value = true
  loadingAuditLogs.value = true
  const selectedGroupId = selectedGroup.value?.id
  try {
    const [userList, groupList, logs] = await Promise.all([
      listUsers(token.value),
      listGroups(token.value),
      listAuditLogs(token.value, 100)
    ])
    users.value = userList
    groups.value = groupList
    auditLogs.value = logs
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
  }
}

async function submitGroup() {
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

async function selectGroup(group: GroupRead) {
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

async function submitGroupMember() {
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

async function removeSelectedGroupMember(member: UserGroupRead) {
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

async function removeGroup(group: GroupRead) {
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

async function refreshAuditLogs() {
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

function auditDetail(log: AuditLogRead) {
  if (!log.detail_json) return '-'
  try {
    const parsed = JSON.parse(log.detail_json)
    return Object.entries(parsed)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join('；')
  } catch {
    return log.detail_json
  }
}

function formatJson(value: Record<string, unknown> | null) {
  if (!value) return '-'
  return JSON.stringify(value, null, 2)
}

function formatPercentScore(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-'
  return `${Math.round(value * 100)}%`
}

function riskLevelLabel(level: string) {
  if (level === 'low') return '低风险'
  if (level === 'medium') return '中风险'
  if (level === 'high') return '高风险'
  return '未评估'
}

function riskLevelType(level: string) {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  if (level === 'high') return 'danger'
  return 'info'
}

function stageStateLabel(state: string) {
  if (state === 'done') return '完成'
  if (state === 'running') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'optional') return '按需'
  return '待处理'
}

function stageStateType(state: string) {
  if (state === 'done') return 'success'
  if (state === 'running') return 'warning'
  if (state === 'failed') return 'danger'
  if (state === 'optional') return 'info'
  return 'info'
}

function formatReportCountMap(value: Record<string, number>) {
  return Object.entries(value)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, count }))
}

function formatPlanSummary(job: DocumentProcessingJobRead) {
  const plan = job.plan_json
  if (!plan) return '-'
  const reader = String(plan.primary_reader || '-')
  const ocr = plan.use_ocr ? '是' : '否'
  const llm = plan.use_llm_preprocessing ? '是' : '否'
  const source = String(plan.source || 'rules')
  return `${reader} / OCR:${ocr} / LLM:${llm} / ${source}`
}

function traceItems(job: DocumentProcessingJobRead) {
  return job.trace_json || []
}

function traceStateLabel(state: string) {
  if (state === 'done') return '完成'
  if (state === 'running') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'skipped') return '跳过'
  return '待处理'
}

function traceStateType(state: string) {
  if (state === 'done') return 'success'
  if (state === 'running') return 'warning'
  if (state === 'failed') return 'danger'
  if (state === 'skipped') return 'info'
  return 'info'
}

function traceDuration(item: IngestionTraceItem) {
  const duration = Number(item.duration_ms || 0)
  if (!duration) return '-'
  if (duration < 1000) return `${duration} ms`
  return `${(duration / 1000).toFixed(1)} s`
}

function traceSummaryRows(item: IngestionTraceItem) {
  const summary = item.summary || {}
  return Object.entries(summary).map(([key, value]) => ({
    key,
    value: String(value ?? '-')
  }))
}

async function confirmDeleteDocument(document: DocumentRead) {
  if (!token.value || !currentUser.value?.is_admin) return
  try {
    await ElMessageBox.confirm(
      `确定删除文档「${document.filename}」吗？这会同时删除数据库记录、源文件和向量库分块。`,
      '删除文档',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  deletingDocumentId.value = document.id
  try {
    await deleteDocument(token.value, document.id)
    selectedChunks.value = []
    selectedChatDocumentIds.value = selectedChatDocumentIds.value.filter((id) => id !== document.id)
    if (selectedDocument.value?.id === document.id) {
      chunkDialogVisible.value = false
      selectedDocument.value = null
    }
    await refreshDocuments()
    ElMessage.success('文档已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  } finally {
    deletingDocumentId.value = null
  }
}

function chunkTypeLabel(chunk: DocumentChunkRead) {
  return String(chunk.metadata.chunk_type || 'unknown')
}

function chunkSourceLabel(chunk: DocumentChunkRead) {
  const page = chunk.metadata.page ? `第 ${chunk.metadata.page} 页` : '无页码'
  const table = chunk.metadata.table_index ? ` / 表 ${chunk.metadata.table_index}` : ''
  return `${page}${table}`
}

function chunkQualityScore(chunk: DocumentChunkRead) {
  const score = Number(chunk.metadata.chunk_quality_score ?? 0)
  return Number.isFinite(score) ? score : 0
}

function chunkQualityLabel(chunk: DocumentChunkRead) {
  const label = String(chunk.metadata.chunk_quality_label || '')
  if (label === 'high') return '质量高'
  if (label === 'medium') return '质量中'
  if (label === 'low') return '质量低'
  return '未评分'
}

function chunkQualityTagType(chunk: DocumentChunkRead) {
  const score = chunkQualityScore(chunk)
  if (score >= 0.85) return 'success'
  if (score >= 0.65) return 'warning'
  return 'danger'
}

function chunkQualityFlags(chunk: DocumentChunkRead) {
  return String(chunk.metadata.chunk_quality_flags || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .join(' / ')
}

function chunkOcrSummary(chunk: DocumentChunkRead) {
  const lineCount = chunk.metadata.ocr_line_count
  const avgScore = chunk.metadata.ocr_avg_score
  if (!lineCount && !avgScore) return ''
  const scoreText = typeof avgScore === 'number' ? avgScore.toFixed(3) : String(avgScore || '-')
  return `OCR 行数 ${lineCount || '-'}，平均置信度 ${scoreText}`
}

async function submitChat() {
  if (!token.value) {
    ElMessage.warning('请先登录后再测试问答')
    return
  }
  const question = chatQuestion.value.trim()
  if (!question) {
    ElMessage.warning('请填写问题')
    return
  }

  const documentIds = [...selectedChatDocumentIds.value]
  const turn: ChatTurn = {
    id: `turn-${Date.now()}`,
    logId: null,
    question,
    documentIds,
    documentNames: selectedDocumentNames(documentIds),
    createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    response: null,
    loading: true,
    error: null,
    progress: 5,
    progressMessage: '准备检索范围'
  }
  chatTurns.value.push(turn)
  chatQuestion.value = ''
  loadingChat.value = true
  await scrollChatToBottom()

  const stopProgress = startChatProgress(turn)
  try {
    const response = await askQuestion(token.value, {
      question,
      document_ids: documentIds.length ? documentIds : undefined,
      top_k: 5
    })
    turn.response = response
    turn.logId = response.log_id
    turn.progress = 100
    turn.progressMessage = '回答完成'
    upsertChatHistoryTurn(turn)
  } catch (error) {
    turn.progress = 100
    turn.progressMessage = '请求失败'
    turn.error = error instanceof Error ? error.message : '问答请求失败'
  } finally {
    stopProgress()
    turn.loading = false
    loadingChat.value = false
    await scrollChatToBottom()
  }
}

function clearConversation() {
  chatTurns.value = []
  evidenceCollapseNames.value = []
}

function showHistoryTurn(turn: ChatTurn) {
  chatTurns.value = [cloneChatTurn(turn)]
  evidenceCollapseNames.value = []
  void scrollChatToBottom()
}

async function deleteHistoryTurn(turn: ChatTurn) {
  if (!token.value || !turn.logId) return
  try {
    await ElMessageBox.confirm('删除后不会再出现在该账号的历史记录中。', '删除问答记录', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }

  deletingChatLogId.value = turn.logId
  try {
    await deleteChatLog(token.value, turn.logId)
    chatHistoryItems.value = chatHistoryItems.value.filter((item) => item.logId !== turn.logId)
    chatTurns.value = chatTurns.value.filter((item) => item.logId !== turn.logId)
    ElMessage.success('问答记录已删除')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '删除问答记录失败')
  } finally {
    deletingChatLogId.value = null
  }
}

function upsertChatHistoryTurn(turn: ChatTurn) {
  if (!turn.logId) return
  const historyTurn = cloneChatTurn(turn)
  const index = chatHistoryItems.value.findIndex((item) => item.logId === turn.logId)
  if (index >= 0) {
    chatHistoryItems.value[index] = historyTurn
    return
  }
  chatHistoryItems.value.push(historyTurn)
}

function cloneChatTurn(turn: ChatTurn): ChatTurn {
  return {
    ...turn,
    documentIds: [...turn.documentIds],
    documentNames: [...turn.documentNames],
    response: turn.response
      ? {
          ...turn.response,
          citations: [...turn.response.citations],
          evidence_rows: [...turn.response.evidence_rows],
          retrieval_trace: [...(turn.response.retrieval_trace || [])],
          sections: { ...turn.response.sections }
        }
      : null
  }
}

function startChatProgress(turn: ChatTurn) {
  const stages = [
    { percent: 12, message: '准备检索范围' },
    { percent: 28, message: '生成问题向量' },
    { percent: 46, message: '检索向量库' },
    { percent: 64, message: '重排候选片段' },
    { percent: 82, message: '调用大模型生成答案' },
    { percent: 94, message: '整理引用与依据' }
  ]
  let index = 0
  const timer = window.setInterval(() => {
    if (!turn.loading || turn.progress >= 94) return
    const stage = stages[Math.min(index, stages.length - 1)]
    turn.progress = Math.max(turn.progress, stage.percent)
    turn.progressMessage = stage.message
    index += 1
  }, 900)
  return () => window.clearInterval(timer)
}

function chatLogToTurn(log: ChatLogRead): ChatTurn {
  const citations = parseLogCitations(log.citations_json)
  const documentIds = [...new Set(citations.map((citation) => citation.document_id))]
  const documentNames = [...new Set(citations.map((citation) => citation.filename).filter(Boolean))]
  return {
    id: `history-${log.id}`,
    logId: log.id,
    question: log.question,
    documentIds,
    documentNames: documentNames.length ? documentNames : selectedDocumentNames(documentIds),
    createdAt: formatTime(log.created_at),
    response: {
      answer: log.answer,
      sections: parseAnswerSections(log.answer),
      evidence_rows: citationsToEvidenceRows(citations),
      citations,
      retrieval_trace: [],
      retrieval_only: false,
      log_id: log.id
    },
    loading: false,
    error: null,
    progress: 100,
    progressMessage: '已完成'
  }
}

function parseLogCitations(value: string | null): Citation[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((item): item is Partial<Citation> => {
        const candidate = item as Partial<Citation>
        return (
          item &&
          typeof item === 'object' &&
          typeof candidate.document_id === 'number' &&
          typeof candidate.filename === 'string'
        )
      })
      .map((item) => ({
        document_id: item.document_id as number,
        filename: item.filename as string,
        chunk_id: item.chunk_id ?? null,
        page: typeof item.page === 'number' ? item.page : null,
        table: typeof item.table === 'string' ? item.table : null,
        chunk_type: item.chunk_type ?? null,
        score: typeof item.score === 'number' ? item.score : null,
        text: typeof item.text === 'string' ? item.text : ''
      }))
  } catch {
    return []
  }
}

function parseAnswerSections(answer: string): AnswerSections {
  const labels: Array<[keyof AnswerSections, string]> = [
    ['classification', '分类判断：'],
    ['conclusion', '结论：'],
    ['basis', '依据：'],
    ['citation', '引用：']
  ]
  const sections: AnswerSections = {
    classification: '-',
    conclusion: answer,
    basis: '-',
    citation: '-'
  }

  for (const [key, label] of labels) {
    const pattern = new RegExp(`${label}([\\s\\S]*?)(?=\\n(?:分类判断|结论|依据|引用)：|$)`)
    const match = answer.match(pattern)
    if (match?.[1]?.trim()) {
      sections[key] = match[1].trim()
    }
  }
  return sections
}

function citationsToEvidenceRows(citations: Citation[]): EvidenceRow[] {
  return citations.map((citation, index) => ({
    index: index + 1,
    score: citation.score,
    filename: citation.filename,
    page: citation.page,
    table: null,
    chunk_id: citation.chunk_id,
    keywords: textPreview(citation.text, 100)
  }))
}

function selectedDocumentNames(ids: number[]) {
  if (!ids.length) return ['全部可访问文档']
  const nameById = new Map(indexedDocuments.value.map((document) => [document.id, document.filename]))
  return ids.map((id) => nameById.get(id) || `文档 ${id}`)
}

function documentScopeLabel(turn: ChatTurn) {
  if (!turn.documentIds.length) return '全部可访问文档'
  if (turn.documentNames.length <= 2) return turn.documentNames.join('、')
  return `${turn.documentNames.slice(0, 2).join('、')} 等 ${turn.documentNames.length} 个文档`
}

function getAnswerSections(response: ChatResponse): AnswerSections {
  return (
    response.sections || {
      classification: '-',
      conclusion: response.answer,
      basis: '-',
      citation: '-'
    }
  )
}

function getEvidenceRows(response: ChatResponse): EvidenceRow[] {
  if (response.evidence_rows?.length) return response.evidence_rows
  return response.citations.map((citation, index) => ({
    index: index + 1,
    score: citation.score,
    filename: citation.filename,
    page: citation.page,
    table: null,
    chunk_id: citation.chunk_id,
    keywords: textPreview(citation.text, 100)
  }))
}

function getRetrievalTrace(response: ChatResponse) {
  return response.retrieval_trace || []
}

function retrievalSourceLabel(source: string | null) {
  const labels: Record<string, string> = {
    original: '原始问题',
    expanded: '扩展检索',
    merged: '融合结果',
    merged_without_reranker: '未重排融合',
    reranked: 'Reranker 精排',
    reranker_failed: '重排失败回退'
  }
  return labels[source || ''] || source || '-'
}

function formatScore(score: number | null) {
  return score === null ? '-' : score.toFixed(3)
}

function formatPage(page: number | null) {
  return page === null ? '-' : String(page)
}

function textPreview(text: string, maxLength = 1600) {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength)}\n...`
}

function citationSourceLabel(citation: Citation) {
  const page = citation.page ? `第 ${citation.page} 页` : '无页码'
  const score = citation.score === null ? '-' : citation.score.toFixed(3)
  return `${citation.filename} / ${page} / ${citation.chunk_type || 'unknown'} / score ${score}`
}

async function scrollChatToBottom() {
  await nextTick()
  if (chatThreadRef.value) {
    chatThreadRef.value.scrollTop = chatThreadRef.value.scrollHeight
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">R</div>
        <div>
          <div class="brand-title">RAG Agent</div>
          <div class="brand-subtitle">企业知识库</div>
        </div>
      </div>

      <nav class="nav-list">
        <button
          class="nav-item"
          :class="{ active: activeView === 'upload' }"
          type="button"
          @click="selectView('upload')"
        >
          <el-icon><UploadFilled /></el-icon>
          <span>文档上传</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: activeView === 'documents', disabled: !isLoggedIn }"
          type="button"
          :disabled="!isLoggedIn"
          @click="selectView('documents')"
        >
          <el-icon><Files /></el-icon>
          <span>文档列表</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: activeView === 'chat', disabled: !isLoggedIn }"
          type="button"
          :disabled="!isLoggedIn"
          @click="selectView('chat')"
        >
          <el-icon><Document /></el-icon>
          <span>问答测试</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: activeView === 'settings', disabled: !isLoggedIn }"
          type="button"
          :disabled="!isLoggedIn"
          @click="selectView('settings')"
        >
          <el-icon><Key /></el-icon>
          <span>系统配置</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="health-dot" :class="{ online: backendOnline }" />
        <span>{{ backendOnline ? '后端在线' : '后端离线' }}</span>
      </div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div>
          <h1>{{ pageTitle }}</h1>
          <p>{{ pageSubtitle }}</p>
        </div>
        <div class="topbar-actions">
          <el-button :icon="Refresh" @click="refreshBackendStatus">刷新状态</el-button>
          <el-button v-if="isLoggedIn" plain @click="logout()">
            {{ currentUser?.username }}，退出
          </el-button>
        </div>
      </header>

      <section v-if="activeView === 'upload'" class="view-grid">
        <div class="primary-column">
          <section class="auth-panel">
            <div class="panel-heading">
              <div>
                <h2>账号访问</h2>
                <p>后端接口会校验 JWT。登录后上传的文档会记录当前用户名，并按权限范围检索。</p>
              </div>
              <el-segmented
                v-if="!isLoggedIn"
                v-model="authMode"
                :options="[
                  { label: '登录', value: 'login' },
                  { label: '注册', value: 'register' }
                ]"
              />
            </div>

            <div v-if="isLoggedIn" class="user-summary">
              <div>
                <strong>{{ currentUser?.username }}</strong>
                <span>{{ currentUser?.is_admin ? '管理员账号' : '普通账号' }}</span>
              </div>
              <el-tag :type="currentUser?.is_admin ? 'success' : 'info'" effect="plain">
                {{ currentUser?.is_admin ? 'Admin' : 'User' }}
              </el-tag>
            </div>

            <el-form v-else class="auth-form" :model="authForm" label-position="top">
              <el-form-item label="用户名">
                <el-input v-model="authForm.username" :prefix-icon="User" placeholder="demo_user" />
              </el-form-item>
              <el-form-item v-if="authMode === 'register'" label="邮箱">
                <el-input v-model="authForm.email" placeholder="demo@example.com" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input
                  v-model="authForm.password"
                  :prefix-icon="Lock"
                  type="password"
                  show-password
                  placeholder="至少 8 位"
                  @keyup.enter="submitAuth"
                />
              </el-form-item>
              <el-button type="primary" :loading="loadingUser" @click="submitAuth">
                {{ authMode === 'login' ? '登录并加载文档' : '注册并登录' }}
              </el-button>
            </el-form>
          </section>

          <section v-if="isLoggedIn" class="upload-panel">
            <div class="panel-heading">
              <div>
                <h2>上传 PDF / Markdown / TXT</h2>
                <p>PDF 会优先提取正文与表格，表格会转成可检索事实，再写入向量库。</p>
              </div>
              <el-tag type="info" effect="plain">单文件 50 MB</el-tag>
            </div>

            <div class="upload-options">
              <div>
                <strong>大模型整理 OCR / 表格切块</strong>
                <span>开启后会更慢，但能提升低质量 OCR 和表格切块的检索质量。</span>
              </div>
              <div class="upload-option-action">
                <span :class="{ active: enableLlmChunkNormalization }">
                  {{ enableLlmChunkNormalization ? '开启' : '关闭' }}
                </span>
                <el-switch v-model="enableLlmChunkNormalization" />
              </div>
            </div>

            <el-upload
              drag
              multiple
              :http-request="handleUpload"
              :show-file-list="false"
              accept=".pdf,.md,.markdown,.txt"
              class="upload-drop"
            >
              <el-icon class="upload-icon"><Cloudy /></el-icon>
              <div class="upload-title">拖拽文件到这里，或点击选择文件</div>
              <div class="upload-copy">支持 PDF、Markdown、TXT；建议先用 5-10 个国标 PDF 做小批量试验。</div>
            </el-upload>

            <div v-if="uploadItems.length" class="upload-list">
              <div v-for="item in uploadItems" :key="item.id" class="upload-row">
                <div class="upload-row-main">
                  <strong>{{ item.filename }}</strong>
                  <div class="upload-row-status">
                    <span>{{ item.message }}</span>
                    <small v-if="uploadProgressMeta(item)">{{ uploadProgressMeta(item) }}</small>
                  </div>
                  <el-button size="small" text :icon="Delete" @click="removeUploadItem(item.id)">
                    清除
                  </el-button>
                </div>
                <el-progress
                  :percentage="item.progress"
                  :status="uploadStatusType(item.status)"
                  :stroke-width="8"
                />
              </div>
            </div>
          </section>

          <section v-else class="locked-panel">
            <h2>请先登录</h2>
            <p>未登录时不会显示文档列表、问答测试，也不能触发上传接口。</p>
          </section>
        </div>

        <aside class="inspector">
          <section class="metric-grid">
            <div class="metric">
              <span>文档数</span>
              <strong>{{ documents.length }}</strong>
            </div>
            <div class="metric">
              <span>已入库</span>
              <strong>{{ indexedCount }}</strong>
            </div>
            <div class="metric">
              <span>失败</span>
              <strong>{{ failedCount }}</strong>
            </div>
          </section>

          <section class="config-panel">
            <h2>当前模型配置</h2>
            <dl>
              <div>
                <dt>Embedding</dt>
                <dd>bge-m3</dd>
              </div>
              <div>
                <dt>Reranker</dt>
                <dd>bge-reranker-v2-m3</dd>
              </div>
              <div>
                <dt>LLM</dt>
                <dd>DeepSeek API</dd>
              </div>
              <div>
                <dt>向量库</dt>
                <dd>ChromaDB</dd>
              </div>
              <div>
                <dt>后端地址</dt>
                <dd>{{ getApiBaseUrl() }}</dd>
              </div>
            </dl>
          </section>

          <section class="notes-panel">
            <h2>测试建议</h2>
            <ul>
              <li><el-icon><CircleCheck /></el-icon>先上传 5-10 个文本型 PDF。</li>
              <li><el-icon><CircleCheck /></el-icon>观察 chunk_count 是否异常偏低。</li>
              <li><el-icon><CircleCheck /></el-icon>表格多的文件优先查看分块质量。</li>
              <li><el-icon><CircleCheck /></el-icon>问答阶段重点验证引用页码。</li>
            </ul>
          </section>
        </aside>
      </section>

      <section v-else-if="activeView === 'documents'" class="view-stack">
        <section v-if="!isLoggedIn" class="locked-panel">
          <h2>请先登录</h2>
          <p>文档列表只展示当前账号有权限访问的文件，未登录时不加载数据。</p>
        </section>

        <section v-else class="document-panel">
          <div class="panel-heading">
            <div>
              <h2>已入库文档</h2>
              <p>状态为 indexed 才代表已经写入向量库。管理员可以删除文档和对应向量。</p>
            </div>
            <el-button :icon="Refresh" :loading="loadingDocuments" @click="refreshDocuments">
              刷新列表
            </el-button>
          </div>

          <div class="table-wrap">
            <el-table :data="documents" v-loading="loadingDocuments" class="document-table" empty-text="暂无文档">
              <el-table-column prop="filename" label="文件名" min-width="260" show-overflow-tooltip />
              <el-table-column label="上传者" width="130">
                <template #default="{ row }">{{ ownerName(row) }}</template>
              </el-table-column>
              <el-table-column prop="file_type" label="类型" width="90" />
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="当前步骤" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">{{ statusMessage(row) }}</template>
              </el-table-column>
              <el-table-column label="分块数" width="100">
                <template #default="{ row }">{{ row.chunk_count }}</template>
              </el-table-column>
              <el-table-column label="大小" width="110">
                <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
              </el-table-column>
              <el-table-column label="上传时间" width="180">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="切块" width="110">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    :icon="View"
                    :disabled="row.status !== 'indexed'"
                    @click="openChunks(row)"
                  >
                    查看
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="任务" width="110">
                <template #default="{ row }">
                  <el-button size="small" :icon="View" @click="openJobs(row)">
                    查看
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="质量" width="110">
                <template #default="{ row }">
                  <el-button size="small" :icon="View" @click="openQualityReport(row)">
                    报告
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="LLM整理" width="120">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    plain
                    :icon="Refresh"
                    :disabled="row.status !== 'indexed'"
                    :loading="normalizingDocumentId === row.id"
                    @click="triggerChunkNormalization(row)"
                  >
                    整理
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column v-if="currentUser?.is_admin" label="权限" width="110">
                <template #default="{ row }">
                  <el-button size="small" :icon="Key" @click="openPermissions(row)">
                    管理
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column v-if="currentUser?.is_admin" label="管理" width="110" fixed="right">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="danger"
                    plain
                    :icon="Delete"
                    :loading="deletingDocumentId === row.id"
                    @click="confirmDeleteDocument(row)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </section>
      </section>

      <section v-else-if="activeView === 'settings'" class="settings-page">
        <section v-if="!isLoggedIn" class="locked-panel">
          <h2>请先登录</h2>
          <p>系统配置需要登录后查看，后续管理员可在这里修改运行参数。</p>
        </section>

        <template v-else>
          <section class="settings-card settings-card-wide demo-overview-card">
            <div class="settings-card-head">
              <div>
                <h2>面试演示总览</h2>
                <p>用一屏说明系统已经从“文档上传”走到“权限感知 RAG 问答”，便于现场展示项目完整度。</p>
              </div>
              <el-tag type="success" effect="plain">RAG Agent Demo</el-tag>
            </div>

            <div class="demo-metric-grid">
              <div v-for="card in demoOverviewCards" :key="card.label" class="demo-metric">
                <span>{{ card.label }}</span>
                <strong>{{ card.label === '总切块数' ? card.value : card.value }}</strong>
                <small>{{ card.note }}</small>
              </div>
              <div class="demo-metric">
                <span>文件体量</span>
                <strong>{{ formatFileSize(totalFileSize) }}</strong>
                <small>本地 data/uploads 管理原文</small>
              </div>
            </div>

            <div class="pipeline-strip">
              <div v-for="(stage, index) in ragPipelineStages" :key="stage.title" class="pipeline-step">
                <div class="pipeline-index">{{ index + 1 }}</div>
                <strong>{{ stage.title }}</strong>
                <p>{{ stage.detail }}</p>
              </div>
            </div>
          </section>

          <section class="settings-card settings-card-wide">
            <div class="settings-card-head">
              <div>
                <h2>能力矩阵</h2>
                <p>这部分可以作为面试时的功能边界说明，区分已跑通、演示版和后续规划。</p>
              </div>
            </div>
            <div class="capability-grid">
              <div v-for="item in capabilityCards" :key="item.title" class="capability-card">
                <div>
                  <strong>{{ item.title }}</strong>
                  <el-tag size="small" effect="plain">{{ item.status }}</el-tag>
                </div>
                <p>{{ item.value }}</p>
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-head">
              <div>
                <h2>模型与服务</h2>
                <p>当前阶段从后端环境变量读取，前端先做只读展示。</p>
              </div>
              <el-tag :type="backendOnline ? 'success' : 'danger'" effect="plain">
                {{ backendOnline ? '后端在线' : '后端离线' }}
              </el-tag>
            </div>
            <div class="settings-kv-grid">
              <div>
                <span>LLM</span>
                <strong>DeepSeek API</strong>
              </div>
              <div>
                <span>Embedding</span>
                <strong>bge-m3</strong>
              </div>
              <div>
                <span>Reranker</span>
                <strong>bge-reranker-v2-m3</strong>
              </div>
              <div>
                <span>向量库</span>
                <strong>ChromaDB</strong>
              </div>
              <div>
                <span>后端地址</span>
                <strong>{{ getApiBaseUrl() }}</strong>
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-head">
              <div>
                <h2>RAG 检索策略</h2>
                <p>这些是后续适合放到管理员配置页的核心参数。</p>
              </div>
            </div>
            <div class="settings-list">
              <div>
                <strong>召回与重排</strong>
                <span>Top-K、最低相似度阈值、Reranker 开关、重排保留数量。</span>
              </div>
              <div>
                <strong>证据约束</strong>
                <span>无证据时返回“未找到”，引用页码、文件名、块 ID 必须随答案返回。</span>
              </div>
              <div>
                <strong>问答日志</strong>
                <span>按用户保存问题、答案、引用来源，支持后续审计和效果回放。</span>
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-head">
              <div>
                <h2>文档处理策略</h2>
                <p>上传页控制开关会影响本次入库任务，不会强制重处理历史文档。</p>
              </div>
            </div>
            <div class="settings-list">
              <div>
                <strong>PDF 探测</strong>
                <span>先判断是否能直接读取正文和表格，失败或质量低时再进入 OCR。</span>
              </div>
              <div>
                <strong>OCR 处理</strong>
                <span>使用 PaddleOCR，记录页码、行置信度和 OCR 来源类型。</span>
              </div>
              <div>
                <strong>LLM 切块整理</strong>
                <span>当前上传开关为 {{ enableLlmChunkNormalization ? '开启' : '关闭' }}，适合表格多或 OCR 质量差的文件。</span>
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-head">
              <div>
                <h2>权限与数据</h2>
                <p>权限必须在后端和检索阶段生效，不能只依赖前端隐藏。</p>
              </div>
              <el-tag :type="currentUser?.is_admin ? 'success' : 'info'" effect="plain">
                {{ currentUser?.is_admin ? '管理员视图' : '普通用户视图' }}
              </el-tag>
            </div>
            <div class="settings-list">
              <div>
                <strong>用户与角色</strong>
                <span>管理员删除文档、查看任务；普通用户只能访问自己有权限的文档。</span>
              </div>
              <div>
                <strong>文件存储</strong>
                <span>原始文件保存到 data/uploads，向量数据保存到 data/chroma，日志保存到 data/logs。</span>
              </div>
              <div>
                <strong>后续可编辑项</strong>
                <span>用户权限、模型路径、OCR 设备、RAG 阈值、任务并发、日志保留周期。</span>
              </div>
            </div>
          </section>

          <section v-if="currentUser?.is_admin" class="settings-card settings-card-wide">
            <div class="settings-card-head">
              <div>
                <h2>用户组 / 部门权限</h2>
                <p>管理员可以创建部门，将用户加入部门，并在文档权限弹窗中按部门批量授权。</p>
              </div>
              <el-button size="small" :icon="Refresh" :loading="loadingGroups" @click="loadPermissionAdminData">
                刷新
              </el-button>
            </div>

            <section class="group-admin-form">
              <el-input v-model="groupForm.name" placeholder="部门名称，例如：法规部" />
              <el-input v-model="groupForm.description" placeholder="部门说明，可选" />
              <el-button type="primary" :loading="loadingGroups" @click="submitGroup">
                创建
              </el-button>
            </section>

            <section class="group-admin-grid">
              <el-table
                :data="groups"
                v-loading="loadingGroups"
                size="small"
                class="admin-table"
                empty-text="暂无用户组 / 部门"
              >
                <el-table-column prop="name" label="部门" min-width="160" show-overflow-tooltip />
                <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
                <el-table-column label="创建时间" width="170">
                  <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="160" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" @click="selectGroup(row)">成员</el-button>
                    <el-button size="small" type="danger" plain @click="removeGroup(row)">
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>

              <section class="group-member-panel">
                <header>
                  <div>
                    <h3>{{ selectedGroup ? selectedGroup.name : '请选择部门' }}</h3>
                    <p>成员会继承该部门被授予的文档读取权限。</p>
                  </div>
                </header>

                <section class="group-member-form">
                  <el-select
                    v-model="groupMemberForm.user_id"
                    filterable
                    placeholder="选择用户"
                    :disabled="!selectedGroup"
                  >
                    <el-option
                      v-for="user in groupMemberOptions"
                      :key="user.id"
                      :label="`${user.username}${user.is_admin ? '（管理员）' : ''}`"
                      :value="user.id"
                    />
                  </el-select>
                  <el-button
                    type="primary"
                    plain
                    :disabled="!selectedGroup"
                    :loading="loadingGroups"
                    @click="submitGroupMember"
                  >
                    加入
                  </el-button>
                </section>

                <el-table
                  :data="selectedGroupMembers"
                  size="small"
                  empty-text="暂无成员"
                >
                  <el-table-column label="用户名" min-width="140">
                    <template #default="{ row }">{{ row.user_username || `用户 ${row.user_id}` }}</template>
                  </el-table-column>
                  <el-table-column label="加入时间" width="150">
                    <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="80">
                    <template #default="{ row }">
                      <el-button size="small" type="danger" plain @click="removeSelectedGroupMember(row)">
                        移除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </section>
            </section>
          </section>

          <section v-if="currentUser?.is_admin" class="settings-card settings-card-wide">
            <div class="settings-card-head">
              <div>
                <h2>审计与权限变更日志</h2>
                <p>记录部门创建、成员变更、用户授权和部门授权，后续可扩展到文档删除与配置变更。</p>
              </div>
              <el-button size="small" :icon="Refresh" :loading="loadingAuditLogs" @click="refreshAuditLogs">
                刷新日志
              </el-button>
            </div>

            <el-table
              :data="auditLogs"
              v-loading="loadingAuditLogs"
              size="small"
              class="audit-table"
              empty-text="暂无权限审计日志"
            >
              <el-table-column label="时间" width="170">
                <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
              </el-table-column>
              <el-table-column prop="action" label="动作" width="190" show-overflow-tooltip />
              <el-table-column label="操作者" width="90">
                <template #default="{ row }">{{ row.actor_user_id || '-' }}</template>
              </el-table-column>
              <el-table-column label="文档" width="90">
                <template #default="{ row }">{{ row.document_id || '-' }}</template>
              </el-table-column>
              <el-table-column label="用户" width="90">
                <template #default="{ row }">{{ row.user_id || '-' }}</template>
              </el-table-column>
              <el-table-column label="部门" width="90">
                <template #default="{ row }">{{ row.group_id || '-' }}</template>
              </el-table-column>
              <el-table-column label="详情" min-width="280" show-overflow-tooltip>
                <template #default="{ row }">{{ auditDetail(row) }}</template>
              </el-table-column>
            </el-table>
          </section>
        </template>
      </section>

      <section v-else-if="activeView === 'chat'" class="qa-workbench">
        <aside class="qa-sidebar">
          <section class="qa-side-section">
            <h2>食品安全监管问答</h2>
            <p>电脑网页端 · 文档输入 · 历史会话</p>
            <el-button type="primary" plain @click="clearConversation">新建对话</el-button>
          </section>

          <section class="qa-side-section">
            <h3>历史记录</h3>
            <p v-if="loadingChatHistory" class="muted">正在加载历史记录...</p>
            <div
              v-for="turn in chatHistory"
              :key="turn.id"
              class="history-row"
            >
              <button class="history-item" type="button" @click="showHistoryTurn(turn)">
                {{ turn.question }}
              </button>
              <el-button
                class="history-delete"
                text
                size="small"
                type="danger"
                :icon="Delete"
                :loading="deletingChatLogId === turn.logId"
                @click.stop="deleteHistoryTurn(turn)"
              />
            </div>
            <p v-if="!chatHistory.length" class="muted">暂无历史问题</p>
          </section>

          <section class="qa-side-section qa-settings">
            <h3>设置</h3>
            <label>检索文档</label>
            <el-select
              v-model="selectedChatDocumentIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              clearable
              filterable
              placeholder="默认检索全部可访问文档"
            >
              <el-option
                v-for="document in indexedDocuments"
                :key="document.id"
                :label="document.filename"
                :value="document.id"
              />
            </el-select>
            <div class="setting-row">
              <span>召回片段数</span>
              <strong>5</strong>
            </div>
            <div class="setting-row">
              <span>输出格式</span>
              <strong>四行结构化</strong>
            </div>
          </section>
        </aside>

        <section v-if="!isLoggedIn" class="locked-panel">
          <h2>请先登录</h2>
          <p>问答接口需要 JWT，并且只会检索当前账号可访问的文档。</p>
        </section>

        <section v-else class="qa-main">
          <header class="qa-title">
            <div>
              <h2>食品安全监管问答系统</h2>
              <div class="qa-tags">
                <el-tag size="small" effect="plain" type="success">API 已配置</el-tag>
                <el-tag size="small" effect="plain">文档输入版</el-tag>
                <el-tag size="small" effect="plain">证据约束回答</el-tag>
              </div>
            </div>
          </header>

          <div ref="chatThreadRef" class="chat-thread">
            <div v-if="!chatTurns.length" class="chat-empty">
              <h3>输入问题开始测试</h3>
              <p>可先选择多个文档，也可以不选，默认在当前账号可访问的全部已入库文档中检索。</p>
            </div>

            <article v-for="turn in chatTurns" :key="turn.id" class="chat-turn">
              <div class="user-bubble">
                <div class="bubble-avatar user-avatar">问</div>
                <div class="bubble-body">
                  <p>{{ turn.question }}</p>
                  <span>{{ documentScopeLabel(turn) }} · {{ turn.createdAt }}</span>
                </div>
              </div>

              <div class="assistant-bubble">
                <div class="bubble-avatar assistant-avatar">答</div>
                <div class="assistant-card">
                  <div v-if="turn.loading" class="chat-progress">
                    <el-skeleton :rows="4" animated />
                    <el-progress :percentage="turn.progress" :stroke-width="8" />
                    <p>{{ turn.progressMessage }}</p>
                  </div>
                  <el-alert v-else-if="turn.error" type="error" :title="turn.error" show-icon :closable="false" />

                  <template v-else-if="turn.response">
                    <div class="answer-lines">
                      <div class="answer-line">
                        <span>分类判断：</span>
                        <p>{{ getAnswerSections(turn.response).classification }}</p>
                      </div>
                      <div class="answer-line">
                        <span>结论：</span>
                        <p>{{ getAnswerSections(turn.response).conclusion }}</p>
                      </div>
                      <div class="answer-line">
                        <span>依据：</span>
                        <p>{{ getAnswerSections(turn.response).basis }}</p>
                      </div>
                      <div class="answer-line">
                        <span>引用：</span>
                        <p>{{ getAnswerSections(turn.response).citation }}</p>
                      </div>
                    </div>

                    <el-collapse v-model="evidenceCollapseNames" class="evidence-collapse">
                      <el-collapse-item :name="turn.id">
                        <template #title>
                          <span class="evidence-title">检索依据</span>
                        </template>
                        <el-table
                          :data="getEvidenceRows(turn.response)"
                          size="small"
                          class="evidence-table"
                          empty-text="无检索依据"
                        >
                          <el-table-column label="片段" width="70">
                            <template #default="{ row }">{{ row.index }}</template>
                          </el-table-column>
                          <el-table-column label="分数" width="90">
                            <template #default="{ row }">{{ formatScore(row.score) }}</template>
                          </el-table-column>
                          <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
                          <el-table-column label="页码" width="80">
                            <template #default="{ row }">{{ formatPage(row.page) }}</template>
                          </el-table-column>
                          <el-table-column label="表号" width="120">
                            <template #default="{ row }">{{ row.table || '-' }}</template>
                          </el-table-column>
                          <el-table-column prop="chunk_id" label="块ID" width="150" show-overflow-tooltip />
                          <el-table-column prop="keywords" label="关键字眼" min-width="260" show-overflow-tooltip />
                        </el-table>
                      </el-collapse-item>
                    </el-collapse>

                    <el-collapse
                      v-if="getRetrievalTrace(turn.response).length"
                      class="retrieval-trace-collapse"
                    >
                      <el-collapse-item :name="`${turn.id}-trace`">
                        <template #title>
                          <span class="evidence-title">链式检索过程</span>
                        </template>
                        <div class="retrieval-trace-list">
                          <article
                            v-for="step in getRetrievalTrace(turn.response)"
                            :key="`${turn.id}-${step.query_index}-${step.source}`"
                            class="retrieval-trace-step"
                          >
                            <div class="retrieval-trace-head">
                              <el-tag size="small" effect="plain">
                                {{ retrievalSourceLabel(step.source) }}
                              </el-tag>
                              <strong>{{ step.query }}</strong>
                              <span>命中 {{ step.hit_count }} 个</span>
                            </div>
                            <el-table
                              :data="step.top_hits"
                              size="small"
                              class="evidence-table"
                              empty-text="无命中"
                            >
                              <el-table-column prop="rank" label="#" width="56" />
                              <el-table-column label="分数" width="90">
                                <template #default="{ row }">{{ formatScore(row.score) }}</template>
                              </el-table-column>
                              <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
                              <el-table-column label="页码" width="80">
                                <template #default="{ row }">{{ formatPage(row.page) }}</template>
                              </el-table-column>
                              <el-table-column label="来源" width="110">
                                <template #default="{ row }">{{ row.retrieval_source || '-' }}</template>
                              </el-table-column>
                              <el-table-column label="关键词" min-width="180" show-overflow-tooltip>
                                <template #default="{ row }">{{ row.matched_terms?.join('、') || '-' }}</template>
                              </el-table-column>
                            </el-table>
                          </article>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
                  </template>
                </div>
              </div>
            </article>
          </div>

          <footer class="chat-composer">
            <el-input
              v-model="chatQuestion"
              placeholder="输入食品安全国家标准相关问题"
              @keyup.enter="submitChat"
            />
            <el-button type="primary" :loading="loadingChat" @click="submitChat">
              发送
            </el-button>
          </footer>
        </section>
      </section>

      <el-dialog v-model="jobDialogVisible" :title="jobDialogTitle" width="82%" class="job-dialog">
        <div v-loading="loadingJobs" class="job-dialog-body">
          <el-table
            :data="selectedJobs"
            size="small"
            class="job-table"
            empty-text="暂无处理任务"
          >
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="stage" label="阶段" width="130" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column label="处理策略" min-width="280" show-overflow-tooltip>
              <template #default="{ row }">{{ formatPlanSummary(row) }}</template>
            </el-table-column>
            <el-table-column prop="message" label="说明" min-width="300" show-overflow-tooltip />
            <el-table-column label="进度" width="130">
              <template #default="{ row }">
                {{ row.progress_current || 0 }} / {{ row.progress_total || 0 }}
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="170">
              <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="结束时间" width="170">
              <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
            </el-table-column>
          </el-table>

          <el-collapse v-if="selectedJobs.length" class="job-detail-collapse">
            <el-collapse-item
              v-for="job in selectedJobs"
              :key="job.id"
              :title="`入库节点追踪 #${job.id}`"
              :name="String(job.id)"
            >
              <section class="job-trace-section">
                <div class="job-trace-head">
                  <h3>节点时间线</h3>
                  <span>展示 FileProbe → StrategyPlanner → Parse/OCR → Normalize → ChunkQuality → Index → Report 的执行结果</span>
                </div>
                <el-timeline v-if="traceItems(job).length" class="job-trace-timeline">
                  <el-timeline-item
                    v-for="item in traceItems(job)"
                    :key="`${job.id}-${item.node}-${item.started_at || item.state}`"
                    :type="traceStateType(item.state)"
                    :timestamp="formatTime(item.started_at || null)"
                    placement="top"
                  >
                    <div class="job-trace-card">
                      <div class="job-trace-title">
                        <strong>{{ item.label || item.node }}</strong>
                        <el-tag :type="traceStateType(item.state)" size="small" effect="plain">
                          {{ traceStateLabel(item.state) }}
                        </el-tag>
                      </div>
                      <p>{{ item.message || '-' }}</p>
                      <p v-if="item.finished_at">结束时间：{{ formatTime(item.finished_at) }}；耗时：{{ traceDuration(item) }}</p>
                      <p v-if="item.error" class="job-trace-error">错误：{{ item.error }}</p>
                      <div v-if="traceSummaryRows(item).length" class="job-trace-summary">
                        <span
                          v-for="row in traceSummaryRows(item)"
                          :key="`${item.node}-${row.key}`"
                        >
                          {{ row.key }}：{{ row.value }}
                        </span>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
                <el-empty v-else description="该任务暂无节点追踪记录" :image-size="72" />
              </section>
              <div class="job-detail-grid">
                <section>
                  <h3>处理策略 Plan</h3>
                  <pre class="json-block">{{ formatJson(job.plan_json) }}</pre>
                </section>
                <section>
                  <h3>文件探测 Probe</h3>
                  <pre class="json-block">{{ formatJson(job.probe_json) }}</pre>
                </section>
                <section>
                  <h3>上传选项 Options</h3>
                  <pre class="json-block">{{ formatJson(job.options_json) }}</pre>
                </section>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-dialog>

      <el-dialog v-model="qualityDialogVisible" :title="qualityDialogTitle" width="78%" class="quality-dialog">
        <div v-loading="loadingQualityReport" class="quality-report-body">
          <template v-if="selectedQualityReport">
            <section class="quality-summary-grid">
              <div class="quality-score-card">
                <span>健康分</span>
                <strong>{{ selectedQualityReport.health_score }}</strong>
              </div>
              <div>
                <span>风险等级</span>
                <strong>
                  <el-tag :type="riskLevelType(selectedQualityReport.risk_level)" effect="plain">
                    {{ riskLevelLabel(selectedQualityReport.risk_level) }}
                  </el-tag>
                </strong>
              </div>
              <div>
                <span>总分块</span>
                <strong>{{ selectedQualityReport.total_chunks }}</strong>
              </div>
              <div>
                <span>覆盖页数</span>
                <strong>{{ selectedQualityReport.unique_pages }}</strong>
              </div>
              <div>
                <span>平均质量</span>
                <strong>{{ formatPercentScore(selectedQualityReport.average_quality_score) }}</strong>
              </div>
              <div>
                <span>低质量块</span>
                <strong>{{ selectedQualityReport.low_quality_count }}</strong>
              </div>
              <div>
                <span>OCR块</span>
                <strong>{{ selectedQualityReport.ocr_chunk_count }}</strong>
              </div>
              <div>
                <span>OCR置信度</span>
                <strong>{{ formatPercentScore(selectedQualityReport.ocr_average_score) }}</strong>
              </div>
              <div>
                <span>表格块</span>
                <strong>{{ selectedQualityReport.table_chunk_count }}</strong>
              </div>
              <div>
                <span>LLM归一化</span>
                <strong>{{ selectedQualityReport.llm_normalized_count }}</strong>
              </div>
              <div>
                <span>修复提示</span>
                <strong>{{ selectedQualityReport.preprocess_repair_count }}</strong>
              </div>
              <div>
                <span>可疑上标</span>
                <strong>{{ selectedQualityReport.suspicious_power_notation_count }}</strong>
              </div>
            </section>

            <section class="quality-section">
              <h3>处理状态</h3>
              <p>{{ selectedQualityReport.status_message || statusLabel(selectedQualityReport.status) }}</p>
              <p v-if="selectedQualityReport.latest_job_message">
                最新任务：{{ selectedQualityReport.latest_job_message }}
              </p>
              <el-progress
                v-if="selectedQualityReport.latest_job_progress_total"
                :percentage="selectedQualityReport.latest_job_progress_percent"
                :stroke-width="8"
              />
            </section>

            <section class="quality-section">
              <h3>节点追踪</h3>
              <el-timeline v-if="selectedQualityReport.latest_job_trace.length" class="job-trace-timeline compact">
                <el-timeline-item
                  v-for="item in selectedQualityReport.latest_job_trace"
                  :key="`${item.node}-${item.started_at || item.state}`"
                  :type="traceStateType(item.state)"
                  :timestamp="formatTime(item.started_at || null)"
                  placement="top"
                >
                  <div class="job-trace-card">
                    <div class="job-trace-title">
                      <strong>{{ item.label || item.node }}</strong>
                      <el-tag :type="traceStateType(item.state)" size="small" effect="plain">
                        {{ traceStateLabel(item.state) }}
                      </el-tag>
                    </div>
                    <p>{{ item.message || '-' }}</p>
                    <p v-if="item.finished_at">结束时间：{{ formatTime(item.finished_at) }}；耗时：{{ traceDuration(item) }}</p>
                  </div>
                </el-timeline-item>
              </el-timeline>
              <p v-else>暂无节点追踪记录，重新入库后的任务会显示完整时间线。</p>
            </section>

            <section class="quality-section">
              <h3>处理阶段概览</h3>
              <div class="quality-stage-list">
                <div
                  v-for="stage in selectedQualityReport.stage_overview"
                  :key="stage.name"
                  class="quality-stage-item"
                >
                  <el-tag :type="stageStateType(stage.state)" size="small" effect="plain">
                    {{ stageStateLabel(stage.state) }}
                  </el-tag>
                  <div>
                    <strong>{{ stage.name }}</strong>
                    <p>{{ stage.detail }}</p>
                    <small v-if="stage.metric">{{ stage.metric }}</small>
                  </div>
                </div>
              </div>
            </section>

            <section class="quality-section">
              <h3>内容类型分布</h3>
              <div class="quality-pill-grid">
                <span v-for="item in formatReportCountMap(selectedQualityReport.chunk_type_counts)" :key="item.key">
                  {{ item.key }}：{{ item.count }}
                </span>
              </div>
            </section>

            <section class="quality-section">
              <h3>质量等级分布</h3>
              <div class="quality-pill-grid">
                <span v-for="item in formatReportCountMap(selectedQualityReport.quality_counts)" :key="item.key">
                  {{ item.key }}：{{ item.count }}
                </span>
              </div>
            </section>

            <section class="quality-section">
              <h3>优化建议</h3>
              <div class="quality-pill-grid quality-risk-grid">
                <span v-for="item in selectedQualityReport.risk_items" :key="item">{{ item }}</span>
              </div>
              <ul class="quality-recommendations">
                <li v-for="item in selectedQualityReport.recommendations" :key="item">{{ item }}</li>
              </ul>
            </section>
          </template>
          <el-empty v-else-if="!loadingQualityReport" description="暂无质量报告" />
        </div>
      </el-dialog>

      <el-dialog v-model="permissionDialogVisible" :title="permissionDialogTitle" width="720px">
        <div v-loading="loadingPermissions" class="permission-dialog-body">
          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="权限在后端文档列表和 RAG 检索阶段都会生效。文档上传者默认拥有访问权限，不需要单独授权。"
          />
          <section class="permission-form">
            <el-select
              v-model="permissionForm.user_id"
              filterable
              placeholder="选择用户"
            >
              <el-option
                v-for="user in permissionUserOptions"
                :key="user.id"
                :label="`${user.username}${user.is_admin ? '（管理员）' : ''}`"
                :value="user.id"
              />
            </el-select>
            <el-checkbox v-model="permissionForm.can_read">可读</el-checkbox>
            <el-checkbox v-model="permissionForm.can_write">可写</el-checkbox>
            <el-button type="primary" @click="submitPermission">保存授权</el-button>
          </section>
          <el-table
            :data="selectedPermissions"
            size="small"
            empty-text="暂无额外授权"
          >
            <el-table-column label="用户" min-width="180">
              <template #default="{ row }">{{ row.user_username || `用户 ${row.user_id}` }}</template>
            </el-table-column>
            <el-table-column label="可读" width="90">
              <template #default="{ row }">
                <el-tag :type="row.can_read ? 'success' : 'info'" effect="plain">
                  {{ row.can_read ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可写" width="90">
              <template #default="{ row }">
                <el-tag :type="row.can_write ? 'success' : 'info'" effect="plain">
                  {{ row.can_write ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="授权时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain @click="revokePermission(row)">
                  撤销
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="permission-section-title">
            <strong>部门授权</strong>
            <span>适合把同一批文档开放给法规部、研发部等用户组。</span>
          </div>

          <section class="permission-form">
            <el-select
              v-model="groupPermissionForm.group_id"
              filterable
              placeholder="选择用户组 / 部门"
            >
              <el-option
                v-for="group in groups"
                :key="group.id"
                :label="group.name"
                :value="group.id"
              />
            </el-select>
            <el-checkbox v-model="groupPermissionForm.can_read">可读</el-checkbox>
            <el-checkbox v-model="groupPermissionForm.can_write">可写</el-checkbox>
            <el-button type="primary" @click="submitGroupPermission">保存部门授权</el-button>
          </section>

          <el-table
            :data="selectedGroupPermissions"
            size="small"
            empty-text="暂无部门授权"
          >
            <el-table-column label="部门" min-width="180">
              <template #default="{ row }">{{ row.group_name || `部门 ${row.group_id}` }}</template>
            </el-table-column>
            <el-table-column label="可读" width="90">
              <template #default="{ row }">
                <el-tag :type="row.can_read ? 'success' : 'info'" effect="plain">
                  {{ row.can_read ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可写" width="90">
              <template #default="{ row }">
                <el-tag :type="row.can_write ? 'success' : 'info'" effect="plain">
                  {{ row.can_write ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="授权时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain @click="revokeGroupPermission(row)">
                  撤销
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-dialog>

      <el-dialog v-model="chunkDialogVisible" :title="chunkDialogTitle" width="78%" class="chunk-dialog">
        <div v-loading="loadingChunks" class="chunk-dialog-body">
          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="这里展示的是已写入 ChromaDB 的文本分块，适合检查表格转写、页码来源和分块边界。"
          />
          <el-empty v-if="!loadingChunks && selectedChunks.length === 0" description="当前文档暂无可展示分块" />
          <div v-else class="chunk-list">
            <article v-for="chunk in selectedChunks" :key="chunk.id" class="chunk-card">
              <header>
                <div>
                  <strong>{{ chunk.id }}</strong>
                  <span>{{ chunkSourceLabel(chunk) }}</span>
                </div>
                <div class="chunk-tags">
                  <el-tag size="small" effect="plain">{{ chunkTypeLabel(chunk) }}</el-tag>
                  <el-tag size="small" effect="plain" :type="chunkQualityTagType(chunk)">
                    {{ chunkQualityLabel(chunk) }} {{ chunkQualityScore(chunk).toFixed(2) }}
                  </el-tag>
                  <el-tag v-if="chunk.metadata.needs_llm_normalization" size="small" effect="plain" type="warning">
                    待归一化
                  </el-tag>
                  <el-tag v-if="chunk.metadata.llm_normalized" size="small" effect="plain" type="success">
                    LLM归一化
                  </el-tag>
                </div>
              </header>
              <div class="chunk-quality-row">
                <span v-if="chunkOcrSummary(chunk)">{{ chunkOcrSummary(chunk) }}</span>
                <span v-if="chunkQualityFlags(chunk)">Flags: {{ chunkQualityFlags(chunk) }}</span>
              </div>
              <p>{{ textPreview(chunk.text, 1800) }}</p>
            </article>
          </div>
        </div>
      </el-dialog>
    </main>
  </div>
</template>
