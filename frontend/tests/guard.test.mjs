import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveGuard } from '../src/router/guard.ts'

const admin = { is_admin: true }
const member = { is_admin: false }

test('a guest route stays open before login', () => {
  assert.deepEqual(resolveGuard({ guest: true }, null, { path: '/login', fullPath: '/login' }), { kind: 'allow' })
})

test('a protected route sends an anonymous visitor to login', () => {
  assert.deepEqual(
    resolveGuard({ requiresAuth: true }, null, { path: '/documents', fullPath: '/documents' }),
    { kind: 'login', redirect: '/documents', warning: undefined }
  )
})

test('an expired token warns before returning to login', () => {
  assert.equal(
    resolveGuard({ requiresAuth: true }, null, { path: '/chat', fullPath: '/chat' }, 'unauthorized').warning,
    '登录状态已失效，请重新登录'
  )
})

test('a normal account cannot open permission pages', () => {
  assert.deepEqual(
    resolveGuard({ requiresAdmin: true }, member, { path: '/permissions', fullPath: '/permissions' }),
    { kind: 'upload', warning: '权限管理仅供管理员使用' }
  )
})

test('a normal account already on the upload page is not redirected again', () => {
  assert.deepEqual(
    resolveGuard({ requiresAdmin: true }, member, { path: '/documents/upload', fullPath: '/documents/upload' }),
    { kind: 'stay' }
  )
})

test('an administrator can open a protected page', () => {
  assert.deepEqual(
    resolveGuard({ requiresAuth: true, requiresAdmin: true }, admin, { path: '/permissions', fullPath: '/permissions' }),
    { kind: 'allow' }
  )
})
