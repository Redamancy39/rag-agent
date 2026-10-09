export interface RetrievalPreferences {
  top_k: number
  rerank_enabled: boolean
  candidate_top_k: number | null
  context_auto: boolean
  context_max_chars: number
}

export const DEFAULT_RETRIEVAL: RetrievalPreferences = {
  top_k: 5, rerank_enabled: true, candidate_top_k: null, context_auto: true, context_max_chars: 16000,
}
export const RETRIEVAL_PRESETS: Record<string, RetrievalPreferences> = {
  fast: { ...DEFAULT_RETRIEVAL, candidate_top_k: 16 },
  balanced: { ...DEFAULT_RETRIEVAL },
  deep: { ...DEFAULT_RETRIEVAL, top_k: 20 },
}

function numberIn(value: unknown, fallback: number, min: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(min, Math.min(max, Math.round(value))) : fallback
}
export function sanitizeRetrieval(value: unknown): RetrievalPreferences {
  const raw = value && typeof value === 'object' ? value as Partial<RetrievalPreferences> : {}
  const top_k = numberIn(raw.top_k, 5, 5, 40)
  return {
    top_k,
    rerank_enabled: typeof raw.rerank_enabled === 'boolean' ? raw.rerank_enabled : true,
    candidate_top_k: raw.candidate_top_k == null ? null : numberIn(raw.candidate_top_k, Math.max(32, top_k * 2), Math.max(16, top_k), 128),
    context_auto: typeof raw.context_auto === 'boolean' ? raw.context_auto : true,
    context_max_chars: numberIn(raw.context_max_chars, 16000, 8000, 64000),
  }
}
export function resolvedContextChars(value: RetrievalPreferences): number {
  return value.context_auto ? Math.max(16000, value.top_k * 1200) : value.context_max_chars
}
export function resolvedCandidateCount(value: RetrievalPreferences): number {
  return Math.max(value.top_k, value.candidate_top_k ?? Math.max(32, value.top_k * 2))
}
export function retrievalPreset(value: RetrievalPreferences): string {
  return Object.keys(RETRIEVAL_PRESETS).find(key => JSON.stringify(RETRIEVAL_PRESETS[key]) === JSON.stringify(value)) || 'custom'
}
export function retrievalPreferenceKey(userId: number): string { return `rag_retrieval_v1_user_${userId}` }
export function loadRetrievalPreferences(storage: Pick<Storage, 'getItem'>, userId: number): RetrievalPreferences {
  try { return sanitizeRetrieval(JSON.parse(storage.getItem(retrievalPreferenceKey(userId)) || 'null')) }
  catch { return { ...DEFAULT_RETRIEVAL } }
}
export function saveRetrievalPreferences(storage: Pick<Storage, 'setItem'>, userId: number, value: RetrievalPreferences): void {
  try { storage.setItem(retrievalPreferenceKey(userId), JSON.stringify(sanitizeRetrieval(value))) }
  catch { /* Storage restrictions do not prevent using the current question's settings. */ }
}
