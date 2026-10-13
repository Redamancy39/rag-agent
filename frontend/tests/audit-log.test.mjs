import test from 'node:test'
import assert from 'node:assert/strict'
import { auditDetail } from '../src/utils/auditLog.ts'

test('audit detail joins every field', () => {
  assert.equal(auditDetail({ detail_json: '{"a":1,"b":true}' }), 'a: 1；b: true')
})

test('missing audit detail is a dash', () => {
  assert.equal(auditDetail({ detail_json: '' }), '-')
})

test('audit detail formats json and keeps invalid text', () => {
  assert.equal(auditDetail({ detail_json: '{"name":"法规部","count":2}' }), 'name: 法规部；count: 2')
  assert.equal(auditDetail({ detail_json: null }), '-')
  assert.equal(auditDetail({ detail_json: 'not-json' }), 'not-json')
})

test('known audit actions use Chinese labels', async () => {
  const { auditActionLabel } = await import('../src/utils/auditLog.ts')
  assert.equal(auditActionLabel('permission.user.deleted'), '撤销用户文档权限')
  assert.equal(auditActionLabel('document_collection.permission.group.created'), '授予部门文档集权限')
  assert.equal(auditActionLabel('group.member.added'), '添加部门成员')
  assert.equal(auditActionLabel('document_collection.documents_moved'), '移动文档到文档集')
})

test('unknown audit actions stay unchanged', async () => {
  const { auditActionLabel } = await import('../src/utils/auditLog.ts')
  assert.equal(auditActionLabel('custom.action'), 'custom.action')
})

test('audit names prefer loaded labels and keep unknown ids', async () => {
  const { auditName } = await import('../src/utils/auditLog.ts')
  const names = new Map([[7, '法规部']])
  assert.equal(auditName(7, names, '部门'), '法规部')
  assert.equal(auditName(8, names, '部门'), '部门 8')
  assert.equal(auditName(null, names, '部门'), '-')
})
