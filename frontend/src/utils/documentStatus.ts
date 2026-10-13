import type { DocumentChunkRead, DocumentProcessingJobRead, DocumentRead, IngestionTraceItem } from '../types.ts'
import { formatTime } from './format.ts'

export interface UploadProgressItem {
  id: string
  document_id?: number
  duplicate?: boolean
  filename: string
  relativePath?: string
  progress: number
  status: 'ready' | 'uploading' | 'indexing' | 'success' | 'error'
  message: string
  stageLabel?: string
  progressCurrent?: number
  progressTotal?: number
  jobUpdatedAt?: string | null
}

export type LlmChunkNormalizationMode = 'auto' | 'enabled' | 'disabled'

export function statusType(status: string) {
  if (status === 'indexed') return 'success'
  if (status === 'failed') return 'danger'
  if ([
    'queued', 'agent_planning', 'file_probe', 'strategy_planner', 'uploaded', 'parsing',
    'parse_ocr', 'preprocessing', 'ocr', 'llm_preprocessing_queued', 'llm_preprocessing',
    'chunking', 'normalize', 'chunk_quality', 'index', 'embedding', 'indexing', 'report'
  ].includes(status)) return 'warning'
  return 'info'
}

export function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: '等待入库', agent_planning: 'Agent 规划', file_probe: '文件探测',
    strategy_planner: '策略规划', uploaded: '已上传', parsing: '读取文件', parse_ocr: '解析 / OCR',
    preprocessing: '质量检查', ocr: 'OCR 识别', llm_preprocessing_queued: 'LLM 排队',
    llm_preprocessing: '大模型整理', chunking: '正在切块', normalize: '归一化整理',
    chunk_quality: '质量评估', index: '准备入库', embedding: '生成向量', indexing: '写入向量库',
    report: '生成报告', indexed: '已入库', failed: '失败'
  }
  return labels[status] || status
}

export function statusMessage(document: DocumentRead) {
  if (document.status === 'failed') return document.error_message || document.status_message || '入库失败'
  if (document.status_message) return document.status_message
  if (document.status === 'indexed') return `入库完成，共 ${document.chunk_count} 个分块`
  return statusLabel(document.status)
}

export function statusProgress(status: string) {
  return ['indexed', 'failed'].includes(status) ? 100 : 0
}

export function uploadStatusType(status: UploadProgressItem['status']) {
  if (status === 'success') return 'success'
  if (status === 'error') return 'exception'
  return undefined
}

export function jobStatusMessage(job: DocumentProcessingJobRead | null) {
  if (!job) return ''
  if (job.status === 'failed') return job.error_message || job.message || '入库失败'
  if (job.stage === 'llm_preprocessing' && job.progress_detail) return job.progress_detail
  return job.message || ''
}

export function jobProgress(job: DocumentProcessingJobRead | null) {
  if (!job) return 0
  if (job.stage !== 'llm_preprocessing' || !job.progress_total) return 0
  return Math.max(0, Math.min(100, Number(job.progress_percent || 0)))
}

export function jobProgressMeta(job: DocumentProcessingJobRead | null) {
  if (!job || job.stage !== 'llm_preprocessing' || !job.progress_total) return null
  return {
    stageLabel: statusLabel(job.stage),
    current: Math.max(0, Number(job.progress_current || 0)),
    total: Math.max(0, Number(job.progress_total || 0))
  }
}

export function uploadProgressMeta(item: UploadProgressItem) {
  const parts: string[] = []
  if (item.stageLabel) parts.push(`阶段：${item.stageLabel}`)
  if (item.progressTotal) parts.push(`已处理：${item.progressCurrent || 0} / ${item.progressTotal} 项`)
  if (item.status === 'uploading') parts.push(`进度：${item.progress}%`)
  if (item.jobUpdatedAt) {
    const time = /(?:Z|[+-]\d{2}:\d{2})$/i.test(item.jobUpdatedAt) ? item.jobUpdatedAt : `${item.jobUpdatedAt}Z`
    parts.push(`最近更新：${formatTime(time)}`)
  }
  return parts.join(' · ')
}

export function llmChunkNormalizationModeLabel(mode: LlmChunkNormalizationMode) {
  const labels: Record<LlmChunkNormalizationMode, string> = { auto: '自动判断', enabled: '强制开启', disabled: '关闭' }
  return labels[mode]
}

export function ownerName(document: DocumentRead) {
  return document.owner_username || `用户 ${document.owner_id}`
}

export function llmCheckLabel(document: DocumentRead) {
  const labels: Record<string, string> = {
    not_run: '未调用', completed: '已检测', partial: '部分成功', failed: '检测失败', running: '检测中', unknown: '记录不足'
  }
  return labels[document.llm_processing?.check_status || 'unknown'] || '记录不足'
}

export function llmCheckType(document: DocumentRead) {
  const state = document.llm_processing?.check_status
  if (state === 'completed') return 'success'
  if (state === 'partial') return 'warning'
  if (state === 'failed') return 'danger'
  return 'info'
}

export function llmNormalizationLabel(document: DocumentRead) {
  const record = document.llm_processing
  if (record?.normalization_status === 'indexed') {
    const count = record.stored_count ?? record.generated_count
    return count ? `已整理 · ${count} 块` : '已整理'
  }
  const labels: Record<string, string> = {
    not_run: '未整理', not_needed: '无需整理', not_generated: '未生成整理块', pending: '已生成 · 待入库',
    index_failed: '已生成 · 入库失败', failed: '整理失败', running: '整理中', recorded: '有整理记录', unknown: '待核查'
  }
  return labels[record?.normalization_status || 'unknown'] || '待核查'
}

export function llmNormalizationType(document: DocumentRead) {
  const state = document.llm_processing?.normalization_status
  if (state === 'indexed' || state === 'recorded') return 'success'
  if (state === 'failed' || state === 'index_failed') return 'danger'
  if (state === 'pending') return 'warning'
  return 'info'
}

export function llmExecutionNote(document: DocumentRead) {
  const record = document.llm_processing
  if (!record) return '暂无执行记录'
  if (record.succeeded_count || record.failed_count) return `成功 ${record.succeeded_count ?? 0} · 失败 ${record.failed_count ?? 0}`
  if (record.screening_status === 'completed') return '规则已筛查'
  return '等待处理记录'
}

export function riskLevelLabel(level: string) {
  if (level === 'low') return '低风险'
  if (level === 'medium') return '中风险'
  if (level === 'high') return '高风险'
  return '未评估'
}

export function riskLevelType(level: string) {
  if (level === 'low') return 'success'
  if (level === 'medium') return 'warning'
  if (level === 'high') return 'danger'
  return 'info'
}

export function stageStateLabel(state: string) {
  if (state === 'done') return '完成'
  if (state === 'running') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'optional') return '按需'
  return '待处理'
}

export function stageStateType(state: string) {
  if (state === 'done') return 'success'
  if (state === 'running') return 'warning'
  if (state === 'failed') return 'danger'
  return 'info'
}

export function formatReportCountMap(value: Record<string, number>) {
  return Object.entries(value).sort((a, b) => b[1] - a[1]).map(([key, count]) => ({ key, count }))
}

export function formatPlanSummary(job: DocumentProcessingJobRead) {
  const plan = job.plan_json
  if (!plan) return '-'
  return `${String(plan.primary_reader || '-')} / OCR:${plan.use_ocr ? '是' : '否'} / LLM:${plan.use_llm_preprocessing ? '是' : '否'} / ${String(plan.source || 'rules')}`
}

export function traceItems(job: DocumentProcessingJobRead) {
  return job.trace_json || []
}

export function traceStateLabel(state: string) {
  if (state === 'done') return '完成'
  if (state === 'running') return '进行中'
  if (state === 'failed') return '失败'
  if (state === 'skipped') return '跳过'
  return '待处理'
}

export function traceStateType(state: string) {
  if (state === 'done') return 'success'
  if (state === 'running') return 'warning'
  if (state === 'failed') return 'danger'
  if (state === 'skipped') return 'info'
  return 'info'
}

export function traceDuration(item: IngestionTraceItem) {
  const duration = Number(item.duration_ms || 0)
  if (!duration) return '-'
  if (duration < 1000) return `${duration} ms`
  return `${(duration / 1000).toFixed(1)} s`
}

export function traceSummaryRows(item: IngestionTraceItem) {
  const summary = item.summary || {}
  const labels: Record<string, string> = {
    enabled: '允许整理', candidate_count: '候选分块', attempted_count: '调用尝试',
    succeeded_count: '成功响应', failed_count: '处理失败', generated_count: '新生成分块',
    stored_count: '整理结果分块', eligible_count: '可处理分块', skip_reason: '跳过原因',
    processed_count: '已处理候选', skipped_count: '未整理候选', request_attempted_count: '实际 API 请求',
    request_succeeded_count: 'API 成功', request_failed_count: 'API 失败', retry_count: '实际重试',
    request_max_calls: '单文档请求上限', max_seconds: '整理时间预算（秒）', elapsed_seconds: '整理耗时（秒）',
    limit_reason: '停止原因', fact_preprocessing_enabled: '前置事实整理'
  }
  return Object.entries(summary).map(([key, value]) => ({ key: labels[key] || key, value: String(value ?? '-') }))
}

export function chunkTypeLabel(chunk: DocumentChunkRead) {
  return String(chunk.metadata.chunk_type || 'unknown')
}

export function chunkSourceLabel(chunk: DocumentChunkRead) {
  if (chunk.location?.label) return chunk.location.label
  const page = chunk.metadata.page ? `第 ${chunk.metadata.page} 页` : '无页码'
  const table = chunk.metadata.table_index ? ` / 表 ${chunk.metadata.table_index}` : ''
  return `${page}${table}`
}

export function chunkQualityScore(chunk: DocumentChunkRead) {
  const score = Number(chunk.metadata.chunk_quality_score ?? 0)
  return Number.isFinite(score) ? score : 0
}

export function chunkQualityLabel(chunk: DocumentChunkRead) {
  const label = String(chunk.metadata.chunk_quality_label || '')
  if (label === 'high') return '质量高'
  if (label === 'medium') return '质量中'
  if (label === 'low') return '质量低'
  return '未评分'
}

export function chunkQualityTagType(chunk: DocumentChunkRead) {
  const score = chunkQualityScore(chunk)
  if (score >= 0.85) return 'success'
  if (score >= 0.65) return 'warning'
  return 'danger'
}

export function chunkQualityFlags(chunk: DocumentChunkRead) {
  return String(chunk.metadata.chunk_quality_flags || '').split(',').map((item) => item.trim()).filter(Boolean).join(' / ')
}

export function chunkOcrSummary(chunk: DocumentChunkRead) {
  const lineCount = chunk.metadata.ocr_line_count
  const avgScore = chunk.metadata.ocr_avg_score
  if (!lineCount && !avgScore) return ''
  const scoreText = typeof avgScore === 'number' ? avgScore.toFixed(3) : String(avgScore || '-')
  return `OCR 行数 ${lineCount || '-'}，平均置信度 ${scoreText}`
}
