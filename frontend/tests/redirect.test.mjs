import test from 'node:test'
import assert from 'node:assert/strict'
import { safeRedirect } from '../src/auth/redirect.ts'

test('safeRedirect rejects protocol-relative and backslash paths', () => {
  assert.equal(safeRedirect('//evil.com'), '/documents/upload')
  assert.equal(safeRedirect('/\\evil'), '/documents/upload')
})

test('safeRedirect rejects login, register and the site root', () => {
  assert.equal(safeRedirect('/login'), '/documents/upload')
  assert.equal(safeRedirect('/register'), '/documents/upload')
  assert.equal(safeRedirect('/'), '/documents/upload')
})

test('safeRedirect keeps an in-app path and query', () => {
  assert.equal(safeRedirect('/chat?x=1'), '/chat?x=1')
})

test('safeRedirect restores the upload page for empty input', () => {
  assert.equal(safeRedirect(undefined), '/documents/upload')
})
