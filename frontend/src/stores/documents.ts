import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listDocumentCollections, listDocuments } from '../api/client.ts'
import { token } from '../auth/session.ts'
import { onSessionReset } from '../auth/session.ts'
import { filterDocuments, paginateItems } from '../utils/documentList.ts'
import type { DocumentCollectionRead, DocumentRead } from '../types.ts'

export const documents = ref<DocumentRead[]>([])
export const documentCollections = ref<DocumentCollectionRead[]>([])
export const documentCollectionFilter = ref<number | 'all' | 'unassigned'>('all')
export const documentLlmFilter = ref('all')
export const documentQuery = ref('')
export const documentStatusFilter = ref('all')
export const documentTypeFilter = ref('all')
export const documentPage = ref(1)
export const documentPageSize = ref(20)
export const loadingDocuments = ref(false)
export const loadingDocumentCollections = ref(false)
export const loadingChunks = ref(false)
export const loadingJobs = ref(false)
export const loadingQualityReport = ref(false)
export const chunkDialogVisible = ref(false)
export const jobDialogVisible = ref(false)
export const qualityDialogVisible = ref(false)
export const deletingDocumentId = ref<number | null>(null)
export const normalizingDocumentId = ref<number | null>(null)
export const selectedChunks = ref<import('../types.ts').DocumentChunkRead[]>([])
export const selectedJobDocument = ref<DocumentRead | null>(null)
export const selectedJobs = ref<import('../types.ts').DocumentProcessingJobRead[]>([])
export const selectedQualityDocument = ref<DocumentRead | null>(null)
export const selectedQualityReport = ref<import('../types.ts').DocumentQualityReportRead | null>(null)
export const selectedDocumentRows = ref<DocumentRead[]>([])
export const selectedDocument = ref<DocumentRead | null>(null)
export const selectedCollection = ref<DocumentCollectionRead | null>(null)
export const selectedUploadCollectionId = ref<number | null>(null)
export const moveTargetCollectionId = ref<number | 'unassigned' | null>(null)
export const selectedChatCollectionIds = ref<number[]>([])
export const documentTable = ref<{ clearSelection: () => void } | null>(null)
export const detailDrawerVisible = ref(false)
export const detailTab = ref<'chunks' | 'jobs' | 'quality'>('chunks')

const afterRefresh: Array<() => void> = []
export function onDocumentsRefreshed(listener: () => void) {
  afterRefresh.push(listener)
}

export const filteredDocuments = computed(() => filterDocuments(documents.value, {
  query: documentQuery.value, collection: documentCollectionFilter.value,
  llm: documentLlmFilter.value, status: documentStatusFilter.value, fileType: documentTypeFilter.value
}))
export const documentPagination = computed(() => paginateItems(filteredDocuments.value, documentPage.value, documentPageSize.value))
watch([documentPage, documentPageSize], () => {
  selectedDocumentRows.value = []
  documentTable.value?.clearSelection()
})
watch(documentPageSize, () => { documentPage.value = 1 })
watch(filteredDocuments, () => {
  if (documentPage.value !== documentPagination.value.page) documentPage.value = documentPagination.value.page
})
export const indexedCount = computed(() => documents.value.filter((item) => item.status === 'indexed').length)
export const failedCount = computed(() => documents.value.filter((item) => item.status === 'failed').length)
export const indexedDocuments = computed(() => documents.value.filter((item) => item.status === 'indexed'))
export const writableDocumentCollections = computed(() => documentCollections.value.filter((item) => item.can_write))
export const processingCount = computed(() => documents.value.filter((item) => !['indexed', 'failed'].includes(item.status)).length)
export const totalChunkCount = computed(() => documents.value.reduce((total, item) => total + Number(item.chunk_count || 0), 0))
export const totalFileSize = computed(() => documents.value.reduce((total, item) => total + Number(item.file_size || 0), 0))

let refreshInflight: Promise<void> | null = null
let refreshPending = false
let refreshTimer: number | null = null
let lastRefreshAt = 0

export function refreshDocuments() {
  if (!token.value) {
    documents.value = []
    refreshPending = false
    return Promise.resolve()
  }
  refreshPending = true
  if (refreshInflight || refreshTimer) return refreshInflight ?? Promise.resolve()
  const wait = lastRefreshAt ? Math.max(0, 3000 - (Date.now() - lastRefreshAt)) : 0
  if (wait > 0) {
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null
      void startDocumentRefresh()
    }, wait)
    return Promise.resolve()
  }
  return startDocumentRefresh()
}

function startDocumentRefresh() {
  if (!refreshPending || refreshInflight || !token.value) return Promise.resolve()
  refreshPending = false
  const task = (async () => {
    loadingDocuments.value = true
    try {
      documents.value = await listDocuments(token.value)
      for (const listener of afterRefresh) listener()
    } catch (error) {
      ElMessage.error(error instanceof Error ? error.message : '文档列表加载失败')
    } finally {
      loadingDocuments.value = false
      lastRefreshAt = Date.now()
    }
  })()
  refreshInflight = task
  return task.finally(() => {
    refreshInflight = null
    if (refreshPending) void refreshDocuments()
  })
}

export async function refreshDocumentCollections() {
  if (!token.value) {
    documentCollections.value = []
    return
  }
  loadingDocumentCollections.value = true
  const selectedCollectionId = selectedCollection.value?.id
  try {
    documentCollections.value = await listDocumentCollections(token.value)
    if (selectedCollectionId) {
      selectedCollection.value = documentCollections.value.find((item) => item.id === selectedCollectionId) || null
    }
    const accessibleCollectionIds = new Set(documentCollections.value.map((item) => item.id))
    if (typeof documentCollectionFilter.value === 'number' && !accessibleCollectionIds.has(documentCollectionFilter.value)) {
      documentCollectionFilter.value = 'all'
    }
    selectedChatCollectionIds.value = selectedChatCollectionIds.value.filter((id) => accessibleCollectionIds.has(id))
    if (selectedUploadCollectionId.value !== null && !writableDocumentCollections.value.some((item) => item.id === selectedUploadCollectionId.value)) {
      selectedUploadCollectionId.value = null
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文档集加载失败')
  } finally {
    loadingDocumentCollections.value = false
  }
}

export function changeDocumentFilter() {
  documentPage.value = 1
  selectedDocumentRows.value = []
}

export function resetDocuments() {
  documents.value = []
  documentCollections.value = []
  selectedDocument.value = null
  selectedChunks.value = []
  selectedJobDocument.value = null
  selectedJobs.value = []
  selectedQualityDocument.value = null
  selectedQualityReport.value = null
  chunkDialogVisible.value = false
  jobDialogVisible.value = false
  qualityDialogVisible.value = false
  detailDrawerVisible.value = false
  detailTab.value = 'chunks'
  selectedDocumentRows.value = []
  selectedCollection.value = null
  selectedUploadCollectionId.value = null
  moveTargetCollectionId.value = null
  selectedChatCollectionIds.value = []
  documentCollectionFilter.value = 'all'
  documentLlmFilter.value = 'all'
  documentQuery.value = ''
  documentStatusFilter.value = 'all'
  documentTypeFilter.value = 'all'
  documentPage.value = 1
}

onSessionReset(resetDocuments)
