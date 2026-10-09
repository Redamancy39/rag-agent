export const DOCUMENT_EXTENSIONS = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'md', 'markdown', 'txt']
export const MAX_DOCUMENT_BYTES = 50 * 1024 * 1024

export interface FolderFile {
  file: File
  relativePath: string
  selected: boolean
  status: 'ready' | 'working' | 'indexed' | 'submitted' | 'failed' | 'duplicate'
  error?: string
}
export interface SkippedFile { relativePath: string; reason: string }
export interface FolderScan { files: FolderFile[]; skipped: SkippedFile[]; total: number }
export type FolderUploader = (file: File, relativePath: string, shouldStop: () => boolean) => Promise<'indexed' | 'submitted' | 'duplicate'>
export class FolderUploadPausedError extends Error {}

export function ignoredPathReason(path: string): string | null {
  const normalized = path.replace(/\\/g, '/')
  const parts = normalized.split('/')
  if (!normalized || normalized.length > 4096 || normalized.startsWith('/') || /^[a-z]:/i.test(normalized)
      || parts.some(part => !part || part === '..' || part === '.' || /[\u0000-\u001f]/.test(part))) return '无效的相对路径'
  const lower = parts.map(part => part.toLowerCase())
  if (lower.some(part => part === '__macosx' || part === '.ds_store' || part.startsWith('._'))) return 'macOS 元数据文件'
  if (lower.some(part => ['$recycle.bin', 'system volume information', 'thumbs.db', 'desktop.ini'].includes(part))) return 'Windows 系统文件'
  if (lower.some(part => part.startsWith('.'))) return '隐藏文件或目录'
  if (lower.slice(0, -1).includes('node_modules')) return '依赖目录'
  const name = parts[parts.length - 1]
  if (name.startsWith('~$') || name.endsWith('~') || /\.(tmp|temp|swp|swo|bak)$/i.test(name)) return '临时或备份文件'
  return null
}

export function scanFolderFiles(files: File[]): FolderScan {
  const result: FolderScan = { files: [], skipped: [], total: files.length }
  const seen = new Set<string>()
  for (const file of files) {
    const relativePath = (file.webkitRelativePath || file.name).replace(/\\/g, '/')
    let reason = ignoredPathReason(relativePath)
    const extension = file.name.split('.').pop()?.toLowerCase() || ''
    if (!reason && !DOCUMENT_EXTENSIONS.includes(extension)) reason = '不支持的文件格式'
    if (!reason && file.size === 0) reason = '空文件'
    if (!reason && file.size > MAX_DOCUMENT_BYTES) reason = '超过单文件 50 MB 限制'
    if (!reason && seen.has(relativePath)) reason = '本次选择中重复的相对路径'
    if (reason) result.skipped.push({ relativePath, reason })
    else {
      seen.add(relativePath)
      result.files.push({ file, relativePath, selected: true, status: 'ready' })
    }
  }
  return result
}

export async function runFolderFiles(files: FolderFile[], upload: FolderUploader, shouldStop: () => boolean): Promise<void> {
  for (const entry of files) {
    if (shouldStop()) break
    if (entry.status !== 'ready' || !entry.selected) continue
    entry.status = 'working'
    try {
      entry.status = await upload(entry.file, entry.relativePath, shouldStop)
    } catch (error) {
      if (error instanceof FolderUploadPausedError) {
        entry.status = 'submitted'
        entry.error = error.message
        break
      }
      entry.status = 'failed'
      entry.error = error instanceof Error ? error.message : '上传或入库失败'
    }
  }
}
