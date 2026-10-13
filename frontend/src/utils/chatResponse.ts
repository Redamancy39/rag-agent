import type {
  AnswerSections, ChatLogRead, ChatResponse, ChatTurn, Citation, EvidenceRow,
  RetrievalTraceHit, SourceLocation
} from '../types.ts'
import { formatScore, formatTime, textPreview } from './format.ts'

export interface AnswerTextSegment { text: string; citationId: number | null }

export function parseAnswerSections(answer: string): AnswerSections {
  const labels: Array<[keyof AnswerSections, string]> = [
    ['classification', '分类判断：'], ['conclusion', '结论：'], ['basis', '依据：'], ['citation', '引用：']
  ]
  const sections: AnswerSections = { classification: '-', conclusion: answer, basis: '-', citation: '-' }
  for (const [key, label] of labels) {
    const match = answer.match(new RegExp(`${label}([\\s\\S]*?)(?=\\n(?:分类判断|结论|依据|引用)：|$)`))
    if (match?.[1]?.trim()) sections[key] = match[1].trim()
  }
  return sections
}

export function normalizeSourceLocation(location: SourceLocation | null | undefined, fallback: Partial<SourceLocation>): SourceLocation {
  const page = location?.page ?? fallback.page ?? null
  const slide = location?.slide ?? fallback.slide ?? null
  const sheet = location?.sheet ?? fallback.sheet ?? null
  const cellRange = location?.cell_range ?? fallback.cell_range ?? null
  const sectionPath = location?.section_path ?? fallback.section_path ?? null
  const paragraphIndex = location?.paragraph_index ?? fallback.paragraph_index ?? null
  const tableIndex = location?.table_index ?? fallback.table_index ?? null
  const blockIndex = location?.block_index ?? fallback.block_index ?? null
  const parts: string[] = []
  if (page !== null) parts.push(`第 ${page} 页`)
  if (slide !== null) parts.push(`第 ${slide} 张幻灯片`)
  if (sectionPath) parts.push(`章节 ${sectionPath}`)
  if (paragraphIndex !== null) parts.push(`段落 ${paragraphIndex}`)
  if (sheet) parts.push(`工作表 ${sheet}`)
  if (cellRange) parts.push(`单元格 ${cellRange}`)
  if (tableIndex !== null) parts.push(`表格 ${tableIndex}`)
  const kind = sheet ? 'sheet' : slide !== null ? 'slide' : page !== null ? 'page'
    : sectionPath ? 'section' : tableIndex !== null ? 'table' : blockIndex !== null ? 'block' : 'document'
  const keyParts = [
    ['page', page], ['slide', slide], ['sheet', sheet], ['cell_range', cellRange],
    ['section_path', sectionPath], ['paragraph_index', paragraphIndex],
    ['table_index', tableIndex], ['block_index', blockIndex]
  ].filter(([, value]) => value !== null && value !== '').map(([key, value]) => `${key}:${value}`)
  return {
    kind: location?.kind || kind, key: location?.key || keyParts.join('|') || 'document',
    label: location?.label || parts.join(' / ') || '文档级',
    page, slide, sheet, cell_range: cellRange, section_path: sectionPath,
    paragraph_index: paragraphIndex, table_index: tableIndex, block_index: blockIndex
  }
}

export function parseLogCitations(value: string | null): Citation[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is Partial<Citation> => {
      const candidate = item as Partial<Citation>
      return Boolean(item) && typeof item === 'object' && typeof candidate.document_id === 'number' && typeof candidate.filename === 'string'
    }).map((item) => ({
      citation_id: typeof item.citation_id === 'number' ? item.citation_id : null,
      document_id: item.document_id as number,
      filename: item.filename as string,
      chunk_id: item.chunk_id ?? null,
      page: typeof item.page === 'number' ? item.page : null,
      slide: typeof item.slide === 'number' ? item.slide : null,
      sheet: typeof item.sheet === 'string' ? item.sheet : null,
      cell_range: typeof item.cell_range === 'string' ? item.cell_range : null,
      section_path: typeof item.section_path === 'string' ? item.section_path : null,
      paragraph_index: typeof item.paragraph_index === 'number' ? item.paragraph_index : null,
      table_index: typeof item.table_index === 'number' ? item.table_index : null,
      block_index: typeof item.block_index === 'number' ? item.block_index : null,
      location: normalizeSourceLocation(item.location, item),
      table: typeof item.table === 'string' ? item.table : null,
      chunk_type: item.chunk_type ?? null,
      score: typeof item.score === 'number' ? item.score : null,
      text: typeof item.text === 'string' ? item.text : ''
    }))
  } catch {
    return []
  }
}

export function documentNamesForIds(ids: number[], lookupName: (id: number) => string | undefined) {
  if (!ids.length) return ['全部可访问文档']
  return ids.map((id) => lookupName(id) || `文档 ${id}`)
}

export function chatLogToTurn(log: ChatLogRead, lookupName: (id: number) => string | undefined): ChatTurn {
  const legacyCitations = parseLogCitations(log.citations_json)
  const response: ChatResponse = log.response
    ? { ...log.response, log_id: log.id }
    : {
        answer: log.answer,
        sections: parseAnswerSections(log.answer),
        evidence_rows: citationsToEvidenceRows(legacyCitations),
        citations: legacyCitations,
        retrieval_trace: log.retrieval_trace || [],
        query_plan: log.query_plan,
        evidence_decision: log.evidence_decision,
        citation_validation: log.citation_validation || {
          valid: true,
          cited_indices: legacyCitations.map((citation, index) => citation.citation_id || index + 1),
          invalid_indices: [], uncited_sections: [], warnings: []
        },
        retrieval_scope: log.retrieval_scope || { requested_document_ids: [], allowed_document_ids: [], top_k: 0 },
        retrieval_only: false,
        log_id: log.id
      }
  if (
    response.sections?.conclusion === '未找到相关答案。' &&
    response.sections?.basis === '未找到可支撑结论的依据。' &&
    /(?:^|\n)结论：/.test(log.answer) && /(?:^|\n)依据：/.test(log.answer)
  ) response.sections = parseAnswerSections(log.answer)
  const citations = response.citations || []
  const requestedDocumentIds = response.retrieval_scope?.requested_document_ids || []
  const documentIds = requestedDocumentIds.length ? [...requestedDocumentIds] : [...new Set(citations.map((citation) => citation.document_id))]
  const documentNames = [...new Set(citations.map((citation) => citation.filename).filter(Boolean))]
  return {
    id: `history-${log.id}`, logId: log.id, question: log.question, documentIds,
    documentNames: documentNames.length ? documentNames : documentNamesForIds(documentIds, lookupName),
    createdAt: formatTime(log.created_at), response, loading: false, error: null,
    progress: 100, progressMessage: '已完成', jobTrace: []
  }
}

export function citationsToEvidenceRows(citations: Citation[]): EvidenceRow[] {
  return citations.map((citation, index) => ({
    index: citation.citation_id || index + 1, score: citation.score, filename: citation.filename,
    page: citation.page, slide: citation.slide, section_path: citation.section_path, sheet: citation.sheet,
    cell_range: citation.cell_range, paragraph_index: citation.paragraph_index, table_index: citation.table_index,
    block_index: citation.block_index, location: citation.location, table: citation.table,
    chunk_id: citation.chunk_id, keywords: textPreview(citation.text, 100)
  }))
}

export function getEvidenceRows(response: ChatResponse): EvidenceRow[] {
  if (response.evidence_rows?.length) return response.evidence_rows
  return citationsToEvidenceRows(response.citations)
}

export function getAnswerSections(response: ChatResponse): AnswerSections {
  return response.sections || { classification: '-', conclusion: response.answer, basis: '-', citation: '-' }
}

export function answerBasisText(response: ChatResponse) {
  const basis = getAnswerSections(response).basis.trim()
  if (basis && basis !== '-') return basis
  return response.citations.length ? '可点击下方来源查看原文片段。' : '暂无可核验依据。'
}

export function legacyCitationNote(response: ChatResponse) {
  if (response.citations.length) return ''
  const note = getAnswerSections(response).citation.trim()
  return ['', '-', '无'].includes(note) ? '' : note
}

export function answerTextSegments(text: string): AnswerTextSegment[] {
  const segments: AnswerTextSegment[] = []
  const pattern = /\[(\d+)\]/g
  let cursor = 0
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > cursor) segments.push({ text: text.slice(cursor, index), citationId: null })
    segments.push({ text: match[0], citationId: Number(match[1]) })
    cursor = index + match[0].length
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), citationId: null })
  return segments.length ? segments : [{ text, citationId: null }]
}

export function citationById(response: ChatResponse, citationId: number) {
  return response.citations.find((citation, index) => (citation.citation_id || index + 1) === citationId)
}

export function citationLocationLabel(citation: Citation | undefined) {
  if (!citation) return '无具体位置'
  if (citation.location?.label) return citation.location.label
  const parts: string[] = []
  if (citation.page) parts.push(`第 ${citation.page} 页`)
  if (citation.slide) parts.push(`第 ${citation.slide} 张幻灯片`)
  if (citation.section_path) parts.push(`章节 ${citation.section_path}`)
  if (citation.paragraph_index !== null) parts.push(`段落 ${citation.paragraph_index}`)
  if (citation.sheet) parts.push(`工作表 ${citation.sheet}`)
  if (citation.cell_range) parts.push(`单元格 ${citation.cell_range}`)
  return parts.length ? parts.join(' / ') : '无具体位置'
}

export function evidenceLocationLabel(item: Pick<EvidenceRow | RetrievalTraceHit, 'page' | 'slide' | 'section_path' | 'sheet' | 'cell_range' | 'location'>) {
  if (item.location?.label) return item.location.label
  const parts: string[] = []
  if (item.page) parts.push(`第 ${item.page} 页`)
  if (item.slide) parts.push(`第 ${item.slide} 张`)
  if (item.section_path) parts.push(item.section_path)
  if (item.sheet) parts.push(`工作表 ${item.sheet}`)
  if (item.cell_range) parts.push(item.cell_range)
  return parts.length ? parts.join(' / ') : '-'
}

export function citationValidationLabel(response: ChatResponse) {
  if (response.knowledge_search === false) return '未查询知识库'
  if (response.sections.classification === '未找到') return '知识库未找到'
  return response.citation_validation?.valid ? '引用校验通过' : '引用校验未通过'
}

export function citationValidationType(response: ChatResponse) {
  if (response.knowledge_search === false || response.sections.classification === '未找到') return 'info'
  return response.citation_validation?.valid ? 'success' : 'danger'
}

export function getRetrievalTrace(response: ChatResponse) { return response.retrieval_trace || [] }
export function getQueryPlan(response: ChatResponse) { return response.query_plan }
export function getEvidenceDecision(response: ChatResponse) { return response.evidence_decision }
export function getRetrievalScope(response: ChatResponse) {
  return response.retrieval_scope || { requested_document_ids: [], allowed_document_ids: [], top_k: 0 }
}

export function joinPlanItems(items: string[] | undefined, fallback = '-') {
  return items && items.length ? items.join('、') : fallback
}

export function formatSynonymExpansions(expansions: Array<Record<string, unknown>> | undefined) {
  if (!expansions?.length) return '-'
  return expansions.map((item) => {
    const canonical = String(item.canonical || '')
    const matched = Array.isArray(item.matched) ? item.matched.map((value) => String(value)).filter(Boolean) : []
    return matched.length ? `${matched.join('/')} -> ${canonical}` : canonical
  }).filter(Boolean).join('；')
}

export function evidenceDecisionType(response: ChatResponse) {
  const decision = getEvidenceDecision(response)
  if (!decision) return 'info'
  return decision.sufficient ? 'success' : 'warning'
}

export function evidenceDecisionLabel(response: ChatResponse) {
  const decision = getEvidenceDecision(response)
  if (!decision) return '未启用'
  return decision.sufficient ? '证据充分' : '证据不足'
}

export function retrievalSourceLabel(source: string | null) {
  const labels: Record<string, string> = {
    normalized: '归一化问题', decomposed: '分解子查询', rewritten: '规则改写查询',
    decomposition_merged: '子查询融合', original: '原始问题', expanded: '扩展检索',
    merged: '融合结果', merged_without_reranker: '未重排融合', reranked: 'Reranker 精排',
    reranked_with_preserved_recall: '精排与召回保留', reranker_failed: '重排失败回退'
  }
  return labels[source || ''] || source || '-'
}

export function retrievalDuration(durationMs: number | null | undefined) {
  if (durationMs === null || durationMs === undefined) return '-'
  if (durationMs < 1000) return `${durationMs} ms`
  return `${(durationMs / 1000).toFixed(2)} s`
}

export function retrievalScoreBreakdown(hit: RetrievalTraceHit) {
  const parts: string[] = []
  if (hit.vector_score !== null && hit.vector_score !== undefined) parts.push(`向量 ${formatScore(hit.vector_score)}`)
  if (hit.bm25_score !== null && hit.bm25_score !== undefined) parts.push(`BM25 ${formatScore(hit.bm25_score)}`)
  if (hit.keyword_score !== null && hit.keyword_score !== undefined) parts.push(`关键词 ${formatScore(hit.keyword_score)}`)
  if (hit.rerank_score !== null && hit.rerank_score !== undefined) parts.push(`精排 ${formatScore(hit.rerank_score)}`)
  return parts.length ? parts.join(' / ') : '-'
}

export function chatStageLabel(stage: string) {
  const labels: Record<string, string> = {
    queued: '等待执行', started: '初始化 RAG 链路', query_normalize: '问题归一化',
    query_decompose: '按需分解查询', retrieve: '检索候选证据', evidence_judge: '审查证据充分性',
    generate: '调用大模型生成答案', citation_validate: '校验答案引用', retrieval_gate: '判断是否查询知识库',
    completed: '回答完成', failed: '问答任务失败'
  }
  return labels[stage] || '问答任务执行中'
}

export function jobTraceStage(item: Record<string, unknown>) { return String(item.stage || 'running') }
export function jobTraceMessage(item: Record<string, unknown>) { return String(item.message || chatStageLabel(jobTraceStage(item))) }
export function jobTraceMeta(item: Record<string, unknown>) {
  const parts: string[] = []
  if (typeof item.progress === 'number') parts.push(`${item.progress}%`)
  if (typeof item.iteration === 'number') parts.push(`第 ${item.iteration} 轮`)
  if (typeof item.hit_count === 'number') parts.push(`候选 ${item.hit_count}`)
  if (typeof item.citation_count === 'number') parts.push(`可用证据 ${item.citation_count}`)
  if (typeof item.query_count === 'number') parts.push(`查询 ${item.query_count} 条`)
  if (typeof item.retry_reason === 'string' && item.retry_reason) parts.push(`状态：${item.retry_reason}`)
  return parts.join(' · ') || '执行中'
}

export function documentScopeLabel(turn: ChatTurn) {
  if (!turn.documentIds.length) return '全部可访问文档'
  if (turn.documentNames.length <= 2) return turn.documentNames.join('、')
  return `${turn.documentNames.slice(0, 2).join('、')} 等 ${turn.documentNames.length} 个文档`
}

export function citationSourceLabel(citation: Citation) {
  const score = citation.score === null ? '-' : citation.score.toFixed(3)
  return `${citation.filename} / ${citationLocationLabel(citation)} / ${citation.chunk_type || 'unknown'} / score ${score}`
}
