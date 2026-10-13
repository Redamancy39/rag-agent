import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ApiError, deleteDocument, getDocumentQualityReport, listDocumentChunks, listDocumentJobs, normalizeDocumentChunks
} from '../api/client'
import { currentUser, token } from '../auth/session'
import { selectedChatDocumentIds } from './chat'
import type { DocumentRead } from '../types'
import {
  chunkDialogVisible, deletingDocumentId, detailDrawerVisible, detailTab, documents, jobDialogVisible,
  loadingChunks, loadingJobs, loadingQualityReport, normalizingDocumentId, qualityDialogVisible,
  refreshDocuments, selectedChunks, selectedDocument, selectedJobDocument, selectedJobs,
  selectedQualityDocument, selectedQualityReport
} from './documents'

export const chunkDialogTitle = computed(() =>
  selectedDocument.value ? `分块预览：${selectedDocument.value.filename}` : '分块预览'
)
export const jobDialogTitle = computed(() =>
  selectedJobDocument.value ? `处理任务：${selectedJobDocument.value.filename}` : '处理任务'
)
export const qualityDialogTitle = computed(() =>
  selectedQualityDocument.value ? `质量报告：${selectedQualityDocument.value.filename}` : '质量报告'
)

export async function openChunks(document: DocumentRead) {
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

export async function openJobs(document: DocumentRead) {
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

export async function openQualityReport(document: DocumentRead) {
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

export async function triggerChunkNormalization(document: DocumentRead) {
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
    ElMessage.error(error instanceof ApiError && error.status === 403 ? '需要写权限' : error instanceof Error ? error.message : 'LLM 整理任务提交失败')
  } finally {
    normalizingDocumentId.value = null
  }
}

export async function confirmDeleteDocument(document: DocumentRead) {
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

export async function openDocumentDetail(document: DocumentRead) {
  selectedDocument.value = document
  detailTab.value = 'chunks'
  detailDrawerVisible.value = true
  await openChunks(document)
}

export async function loadDetailTab(name: 'chunks' | 'jobs' | 'quality') {
  const document = selectedDocument.value
  if (!document) return
  detailTab.value = name
  if (name === 'chunks') await openChunks(document)
  if (name === 'jobs') await openJobs(document)
  if (name === 'quality') await openQualityReport(document)
}
