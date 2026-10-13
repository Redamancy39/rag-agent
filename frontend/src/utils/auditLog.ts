import type { AuditLogRead } from '../types.ts'

const ACTION_LABELS: Record<string, string> = {
  'permission.user.created': '授予用户文档权限',
  'permission.user.updated': '更新用户文档权限',
  'permission.user.deleted': '撤销用户文档权限',
  'permission.group.created': '授予部门文档权限',
  'permission.group.updated': '更新部门文档权限',
  'permission.group.deleted': '撤销部门文档权限',
  'group.created': '创建部门',
  'group.updated': '更新部门',
  'group.deleted': '删除部门',
  'group.member.added': '添加部门成员',
  'group.member.removed': '移除部门成员',
  'document_collection.created': '创建文档集',
  'document_collection.updated': '更新文档集',
  'document_collection.deleted': '删除文档集',
  'document_collection.documents_moved': '移动文档到文档集',
  'document_collection.permission.user.created': '授予用户文档集权限',
  'document_collection.permission.user.updated': '更新用户文档集权限',
  'document_collection.permission.user.deleted': '撤销用户文档集权限',
  'document_collection.permission.group.created': '授予部门文档集权限',
  'document_collection.permission.group.updated': '更新部门文档集权限',
  'document_collection.permission.group.deleted': '撤销部门文档集权限'
}

export function auditActionLabel(action: string) {
  return ACTION_LABELS[action] || action
}

export function auditName(id: number | null, names: ReadonlyMap<number, string>, fallback: string) {
  if (id == null) return '-'
  return names.get(id) || `${fallback} ${id}`
}

export function auditDetail(log: Pick<AuditLogRead, 'detail_json'>) {
  if (!log.detail_json) return '-'
  try {
    const parsed = JSON.parse(log.detail_json) as Record<string, unknown>
    return Object.entries(parsed)
      .map(([key, value]) => `${key}: ${String(value)}`)
      .join('；')
  } catch {
    return log.detail_json
  }
}
