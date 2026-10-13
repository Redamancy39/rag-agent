export interface GuardMeta {
  guest?: boolean
  requiresAuth?: boolean
  requiresAdmin?: boolean
}

export interface GuardUser {
  is_admin: boolean
}

export type GuardDecision =
  | { kind: 'allow' }
  | { kind: 'login'; redirect: string; warning?: string }
  | { kind: 'upload'; warning: string }
  | { kind: 'stay' }

export function resolveGuard(
  meta: GuardMeta,
  user: GuardUser | null,
  location: { path: string; fullPath: string },
  authFailure: 'unauthorized' | null = null
): GuardDecision {
  if (meta.guest) return { kind: 'allow' }
  if (!meta.requiresAuth && !meta.requiresAdmin) return { kind: 'allow' }
  if (!user) {
    return {
      kind: 'login',
      redirect: location.fullPath,
      warning: authFailure === 'unauthorized' ? '登录状态已失效，请重新登录' : undefined
    }
  }
  if (meta.requiresAdmin && !user.is_admin) {
    if (location.path === '/documents/upload') return { kind: 'stay' }
    return { kind: 'upload', warning: '权限管理仅供管理员使用' }
  }
  return { kind: 'allow' }
}
