import { ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { getDocument, listDocumentJobs, uploadDocument } from '../api/client'
import { sessionVersion, token } from '../auth/session'
import { onSessionReset } from '../auth/session'
import type { DocumentProcessingJobRead, DocumentRead } from '../types'
import { FolderUploadPausedError, type FolderUploader } from '../utils/folderFiles'
import {
  jobProgress, jobProgressMeta, jobStatusMessage, statusLabel, statusMessage, statusProgress,
  type UploadProgressItem
} from '../utils/documentStatus'
import {
  documents, onDocumentsRefreshed, refreshDocuments, selectedUploadCollectionId
} from './documents'
import { llmChunkNormalizationMode } from './uploadForm'

export const uploadItems = ref<UploadProgressItem[]>([])
let uploadSequence = 0

export function resetUploadQueue() {
  uploadItems.value = []
}

onSessionReset(resetUploadQueue)
onDocumentsRefreshed(syncUploadItemsWithDocuments)

export function removeUploadItem(id: string) {
  uploadItems.value = uploadItems.value.filter((item) => item.id !== id)
}

export function syncUploadItemsWithDocuments() {
  const byId = new Map(documents.value.map((document) => [document.id, document]))
  for (const item of uploadItems.value) {
    if (!item.document_id) continue
    if (item.duplicate) continue
    const document = byId.get(item.document_id)
    if (!document) continue
    applyDocumentStatusToUploadItem(item, document)
  }
}

export function applyDocumentStatusToUploadItem(item: UploadProgressItem, document: DocumentRead) {
  item.progress = statusProgress(document.status)
  item.message = statusMessage(document)
  item.stageLabel = statusLabel(document.status)
  if (document.status !== 'llm_preprocessing') {
    item.progressCurrent = undefined
    item.progressTotal = undefined
  } else if (item.progressTotal) {
    item.progress = Math.min(100, Math.round((item.progressCurrent || 0) / item.progressTotal * 100))
  }
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

export async function handleUpload(options: UploadRequestOptions) {
  if (!token.value) {
    ElMessage.warning('请先登录后再上传文档')
    return
  }
  try {
    const { document } = await submitUpload(options.file, uploadContext())
    options.onSuccess?.(document)
  } catch { /* The upload row already contains the failure. */ }
}

export function uploadContext() {
  return {
    token: token.value,
    version: sessionVersion.value,
    mode: llmChunkNormalizationMode.value,
    collectionId: selectedUploadCollectionId.value
  }
}

export async function submitUpload(
  file: File,
  context: ReturnType<typeof uploadContext>,
  relativePath?: string,
  poll = true
) {
  const uploadItem: UploadProgressItem = {
    id: `${Date.now()}-${++uploadSequence}`,
    filename: file.name,
    relativePath,
    progress: 0,
    status: 'uploading',
    message: '正在上传原始文件'
  }
  uploadItems.value.unshift(uploadItem)

  try {
    const document = await uploadDocument(
      context.token,
      file,
      context.mode,
      context.collectionId,
      (progress) => {
        uploadItem.progress = progress
        if (progress >= 100) {
          uploadItem.status = 'indexing'
          uploadItem.message = '上传完成，等待后台解析入库'
        }
      },
      relativePath
    )
    uploadItem.document_id = document.id
    if (document.duplicate) {
      uploadItem.duplicate = true
      uploadItem.status = 'success'
      uploadItem.progress = 100
      uploadItem.stageLabel = '重复跳过'
      uploadItem.message = `${document.duplicate_reason || '已跳过重复内容'}；已有文档状态：${statusLabel(document.status)}`
      if (context.version === sessionVersion.value) await refreshDocuments()
      return { document, uploadItem }
    }
    uploadItem.progress = statusProgress(document.status)
    uploadItem.status = document.status === 'failed' ? 'error' : 'indexing'
    uploadItem.message = statusMessage(document)
    if (context.version === sessionVersion.value) {
      await refreshDocuments()
      if (poll) void pollUploadStatus(uploadItem, document.id)
    }
    return { document, uploadItem }
  } catch (error) {
    uploadItem.status = 'error'
    uploadItem.message = error instanceof Error ? error.message : '上传失败'
    throw error
  }
}

export function createFolderUploader(): FolderUploader {
  const context = uploadContext()
  return async (file, relativePath, shouldStop) => {
    const stopped = () => shouldStop() || context.version !== sessionVersion.value || token.value !== context.token
    if (stopped()) throw new Error('登录状态已变化，未提交该文件')
    const { document, uploadItem } = await submitUpload(file, context, relativePath, false)
    if (document.duplicate) return 'duplicate'
    let current: DocumentRead = document
    applyDocumentStatusToUploadItem(uploadItem, current)
    while (!stopped()) {
      if (current.status === 'indexed') { await refreshDocuments(); return 'indexed' }
      if (current.status === 'failed') throw new Error(statusMessage(current))
      await new Promise(resolve => window.setTimeout(resolve, 2000))
      if (stopped()) break
      try {
        current = await getDocument(context.token, document.id)
        const jobs = await listDocumentJobs(context.token, document.id)
        applyProcessingJob(uploadItem, current, jobs[0] || null)
      }
      catch {
        uploadItem.message = '文件已提交，暂时无法查询结果；恢复连接后可在文档列表查看'
        throw new FolderUploadPausedError('文件已提交，但状态查询失败；请先恢复连接再继续上传')
      }
    }
    if (context.version === sessionVersion.value) void pollUploadStatus(uploadItem, document.id)
    return 'submitted'
  }
}

export function applyProcessingJob(
  item: UploadProgressItem,
  document: DocumentRead,
  job: DocumentProcessingJobRead | null
) {
  applyDocumentStatusToUploadItem(item, document)
  const meta = jobProgressMeta(job)
  item.stageLabel = meta?.stageLabel || statusLabel(document.status)
  item.progressCurrent = meta?.current
  item.progressTotal = meta?.total
  item.jobUpdatedAt = job?.updated_at
  if (meta && document.status !== 'indexed' && document.status !== 'failed') item.progress = jobProgress(job)
  const detail = jobStatusMessage(job)
  if (detail) item.message = detail
}

const UPLOAD_POLL_LIMIT = 30 * 60 * 1000

export async function pollUploadStatus(item: UploadProgressItem, documentId: number) {
  if (!token.value) return
  const startedVersion = sessionVersion.value
  const startedAt = Date.now()
  for (let attempt = 0; ; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
    if (Date.now() - startedAt >= UPLOAD_POLL_LIMIT) {
      item.status = 'indexing'
      item.message = '仍在后台处理，请到文档列表查看'
      return
    }
    if (!token.value || startedVersion !== sessionVersion.value || !uploadItems.value.some(row => row.id === item.id)) return
    try {
      const document = await getDocument(token.value, documentId)
      const jobs = await listDocumentJobs(token.value, documentId)
      const latestJob = jobs[0] || null
      applyProcessingJob(item, document, latestJob)
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
}
