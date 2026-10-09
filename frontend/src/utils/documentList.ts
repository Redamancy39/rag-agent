import type { DocumentRead } from '../types'

export interface DocumentFilters {
  query: string
  collection: number | 'all' | 'unassigned'
  llm: string
  status: string
  fileType: string
}

export function filterDocuments(documents: DocumentRead[], filters: DocumentFilters): DocumentRead[] {
  const query = filters.query.trim().toLocaleLowerCase()
  return documents.filter(document => {
    if (query && !document.filename.toLocaleLowerCase().includes(query)) return false
    if (filters.collection === 'unassigned' && document.collection_id !== null) return false
    if (typeof filters.collection === 'number' && document.collection_id !== filters.collection) return false
    if (filters.status === 'processing' && ['indexed', 'failed'].includes(document.status)) return false
    if (['indexed', 'failed'].includes(filters.status) && document.status !== filters.status) return false
    if (filters.fileType !== 'all' && document.file_type.toLowerCase() !== filters.fileType) return false
    const record = document.llm_processing
    const state = record?.check_status || 'unknown'
    switch (filters.llm) {
      case 'checked': return ['completed', 'partial'].includes(state)
      case 'normalized': return ['indexed', 'recorded'].includes(record?.normalization_status || '')
      case 'not_run': return state === 'not_run'
      case 'failed': return ['partial', 'failed'].includes(state) || record?.normalization_status === 'index_failed'
      case 'unknown': return state === 'unknown'
      case 'running': return state === 'running'
      default: return true
    }
  })
}

export function paginateItems<T>(items: T[], page: number, pageSize: number): { items: T[]; page: number } {
  const size = Math.max(1, pageSize)
  const current = Math.max(1, Math.min(page, Math.ceil(items.length / size) || 1))
  return { items: items.slice((current - 1) * size, current * size), page: current }
}
