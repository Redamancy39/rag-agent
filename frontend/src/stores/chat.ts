import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createChatJob, deleteChatLog, getChatJob, listChatHistory } from '../api/client'
import { currentUser, onSessionReset, token } from '../auth/session'
import type { ChatJobRead, ChatResponse, ChatTurn } from '../types'
import { chatLogToTurn, chatStageLabel, documentNamesForIds } from '../utils/chatResponse'
import {
  DEFAULT_RETRIEVAL, loadRetrievalPreferences, saveRetrievalPreferences, sanitizeRetrieval,
  type RetrievalPreferences
} from '../utils/retrievalPreferences'
import { indexedDocuments, selectedChatCollectionIds } from './documents'

export const loadingChat = ref(false)
export const loadingChatHistory = ref(false)
export const deletingChatLogId = ref<number | null>(null)
export const selectedChatDocumentIds = ref<number[]>([])
export const retrievalPreferences = ref<RetrievalPreferences>({ ...DEFAULT_RETRIEVAL })
export const chatQuestion = ref('')
export const chatTurns = ref<ChatTurn[]>([])
export const chatHistoryItems = ref<ChatTurn[]>([])
export const evidenceCollapseNames = ref<string[]>([])
export const chatThreadRef = ref<HTMLElement | null>(null)

watch(retrievalPreferences, value => {
  if (currentUser.value) saveRetrievalPreferences(localStorage, currentUser.value.id, value)
}, { deep: true, flush: 'sync' })

export const selectedCollectionDocumentIds = computed(() => {
  if (!selectedChatCollectionIds.value.length) return []
  const collectionIds = new Set(selectedChatCollectionIds.value)
  return indexedDocuments.value
    .filter(
      (document) =>
        document.collection_id !== null &&
        collectionIds.has(document.collection_id)
    )
    .map((document) => document.id)
})

export const effectiveChatDocumentIds = computed(() =>
  [...new Set([
    ...selectedCollectionDocumentIds.value,
    ...selectedChatDocumentIds.value
  ])]
)

export const chatHistory = computed(() => [...chatHistoryItems.value].reverse())

export function resetChat() {
  selectedChatDocumentIds.value = []
  chatTurns.value = []
  chatHistoryItems.value = []
  evidenceCollapseNames.value = []
  retrievalPreferences.value = { ...DEFAULT_RETRIEVAL }
}

onSessionReset(resetChat)

export function applyAccountRetrievalPreferences(userId: number) {
  retrievalPreferences.value = loadRetrievalPreferences(localStorage, userId)
}

export async function loadChatHistory(options: { hydrateConversation?: boolean } = {}) {
  if (!token.value) {
    chatTurns.value = []
    chatHistoryItems.value = []
    return
  }
  loadingChatHistory.value = true
  try {
    const logs = await listChatHistory(token.value, 50)
    const turns = logs.slice().reverse().map((log) => chatLogToTurn(log, documentFilename))
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

export function fillChatQuestion(text: string) {
  chatQuestion.value = text
}

export async function submitChat() {
  if (loadingChat.value) return
  if (!token.value) {
    ElMessage.warning('请先登录后再测试问答')
    return
  }
  const question = chatQuestion.value.trim()
  if (!question) {
    ElMessage.warning('请填写问题')
    return
  }

  const documentIds = [...effectiveChatDocumentIds.value]
  const questionPreferences = sanitizeRetrieval(retrievalPreferences.value)
  if (selectedChatCollectionIds.value.length && !documentIds.length) {
    ElMessage.warning('所选文档集中暂无已入库文档')
    return
  }
  const turn = reactive<ChatTurn>({
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
    progressMessage: '创建问答任务',
    jobTrace: []
  })
  chatTurns.value.push(turn)
  chatQuestion.value = ''
  loadingChat.value = true
  await scrollChatToBottom()

  try {
    const job = await createChatJob(token.value, {
      question,
      document_ids: documentIds.length ? documentIds : undefined,
      ...questionPreferences
    })
    updateTurnFromChatJob(turn, job)
    const response = await pollChatJob(turn, job.id)
    const activeTurn = resolveChatTurn(turn)
    activeTurn.response = response
    activeTurn.logId = response.log_id
    activeTurn.progress = 100
    activeTurn.progressMessage = '回答完成'
    upsertChatHistoryTurn(activeTurn)
  } catch (error) {
    const activeTurn = resolveChatTurn(turn)
    activeTurn.progress = 100
    activeTurn.progressMessage = '请求失败'
    activeTurn.error = error instanceof Error ? error.message : '问答请求失败'
  } finally {
    resolveChatTurn(turn).loading = false
    loadingChat.value = false
    await scrollChatToBottom()
  }
}

export async function pollChatJob(turn: ChatTurn, jobId: number): Promise<ChatResponse> {
  if (!token.value) throw new Error('请先登录')
  for (let attempt = 0; attempt < 600; attempt += 1) {
    if (!token.value) throw new Error('登录状态已失效')
    const job = await getChatJob(token.value, jobId)
    updateTurnFromChatJob(turn, job)
    if (job.status === 'completed') {
      if (!job.response_json) {
        throw new Error('问答任务已完成，但后端未返回答案')
      }
      return job.response_json
    }
    if (job.status === 'failed') {
      throw new Error(job.error_message || job.message || '问答任务失败')
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
  throw new Error('问答任务等待超时')
}

export function resolveChatTurn(turn: ChatTurn) {
  return chatTurns.value.find((item) => item.id === turn.id) || turn
}

export function updateTurnFromChatJob(turn: ChatTurn, job: ChatJobRead) {
  const activeTurn = resolveChatTurn(turn)
  activeTurn.progress = Math.max(activeTurn.progress, job.progress_percent || 1)
  activeTurn.progressMessage = job.message || job.progress_detail || chatStageLabel(job.stage)
  activeTurn.jobTrace = job.trace_json || []
}

export function chatJobTraceItems(turn: ChatTurn) {
  return turn.jobTrace.slice(-8)
}

export function clearConversation() {
  chatTurns.value = []
  evidenceCollapseNames.value = []
}

export function showHistoryTurn(turn: ChatTurn) {
  chatTurns.value = [cloneChatTurn(turn)]
  evidenceCollapseNames.value = []
  void scrollChatToBottom()
}

export async function deleteHistoryTurn(turn: ChatTurn) {
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

export function upsertChatHistoryTurn(turn: ChatTurn) {
  if (!turn.logId) return
  const historyTurn = cloneChatTurn(turn)
  const index = chatHistoryItems.value.findIndex((item) => item.logId === turn.logId)
  if (index >= 0) {
    chatHistoryItems.value[index] = historyTurn
    return
  }
  chatHistoryItems.value.push(historyTurn)
}

export function cloneChatTurn(turn: ChatTurn): ChatTurn {
  return {
    ...turn,
    documentIds: [...turn.documentIds],
    documentNames: [...turn.documentNames],
    jobTrace: [...turn.jobTrace],
    response: turn.response
      ? {
          ...turn.response,
          citations: [...turn.response.citations],
          evidence_rows: [...turn.response.evidence_rows],
          retrieval_trace: [...(turn.response.retrieval_trace || [])],
          query_plan: turn.response.query_plan ? { ...turn.response.query_plan } : null,
          evidence_decision: turn.response.evidence_decision
            ? { ...turn.response.evidence_decision }
            : null,
          citation_validation: {
            ...turn.response.citation_validation,
            cited_indices: [...(turn.response.citation_validation?.cited_indices || [])],
            invalid_indices: [...(turn.response.citation_validation?.invalid_indices || [])],
            uncited_sections: [...(turn.response.citation_validation?.uncited_sections || [])],
            warnings: [...(turn.response.citation_validation?.warnings || [])]
          },
          retrieval_scope: {
            ...turn.response.retrieval_scope,
            requested_document_ids: [
              ...(turn.response.retrieval_scope?.requested_document_ids || [])
            ],
            allowed_document_ids: [
              ...(turn.response.retrieval_scope?.allowed_document_ids || [])
            ]
          },
          sections: { ...turn.response.sections }
        }
      : null
  }
}

export function documentFilename(id: number) {
  return indexedDocuments.value.find((document) => document.id === id)?.filename
}

export function selectedDocumentNames(ids: number[]) {
  return documentNamesForIds(ids, documentFilename)
}

export async function scrollChatToBottom() {
  await nextTick()
  if (chatThreadRef.value) {
    chatThreadRef.value.scrollTop = chatThreadRef.value.scrollHeight
  }
}
