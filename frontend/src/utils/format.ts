export function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

export function formatJson(value: Record<string, unknown> | null) {
  if (!value) return '-'
  return JSON.stringify(value, null, 2)
}

export function formatPercentScore(value: number | null) {
  if (value === null || Number.isNaN(value)) return '-'
  return `${Math.round(value * 100)}%`
}

export function formatScore(score: number | null) {
  return score === null ? '-' : score.toFixed(3)
}

export function formatPage(page: number | null) {
  return page === null ? '-' : String(page)
}

export function textPreview(text: string, maxLength = 1600) {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength)}\n...`
}
