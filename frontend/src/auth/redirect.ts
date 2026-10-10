const WORKBENCH_HOME = '/documents/upload'

export function safeRedirect(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return WORKBENCH_HOME
  }
  const path = value.split(/[?#]/, 1)[0] ?? ''
  if (path === '/login' || path === '/register' || path === '/') return WORKBENCH_HOME
  return value
}
