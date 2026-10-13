import test from 'node:test'
import assert from 'node:assert/strict'
import { llmCheckLabel, riskLevelLabel, stageStateLabel, statusLabel, statusMessage, traceStateLabel, uploadProgressMeta } from '../src/utils/documentStatus.ts'

test('failed status prefers the error message', () => {
  assert.equal(statusMessage({ status: 'failed', error_message: null, status_message: '任务失败', chunk_count: 0 }), '任务失败')
})

test('status and risk labels cover known and unknown values', () => {
  assert.equal(statusMessage({ status: 'failed', error_message: '解析失败', status_message: null, chunk_count: 0 }), '解析失败')
  assert.equal(statusMessage({ status: 'indexed', error_message: null, status_message: null, chunk_count: 3 }), '入库完成，共 3 个分块')
  assert.equal(llmCheckLabel({ llm_processing: { check_status: 'running' } }), '检测中')
  assert.equal(riskLevelLabel('mystery'), '未评估')
  assert.equal(stageStateLabel('optional'), '按需')
  assert.equal(traceStateLabel('skipped'), '跳过')
})

test('unknown document status is returned unchanged', () => {
  assert.equal(statusLabel('custom_stage'), 'custom_stage')
  assert.equal(statusLabel('indexed'), '已入库')
})

test('upload progress appends Z when the timestamp has no timezone', () => {
  const withZone = uploadProgressMeta({
    id: '1', filename: 'a.txt', progress: 10, status: 'indexing', message: '',
    stageLabel: '写入向量库', jobUpdatedAt: '2026-10-13T01:02:03Z'
  })
  assert.match(withZone, /阶段：写入向量库/)
  const withoutZone = uploadProgressMeta({
    id: '1', filename: 'a.txt', progress: 40, status: 'uploading', message: '',
    progressCurrent: 1, progressTotal: 4, jobUpdatedAt: '2026-10-13T01:02:03'
  })
  assert.match(withoutZone, /进度：40%/)
  assert.match(withoutZone, /已处理：1 \/ 4 项/)
  assert.match(withoutZone, /最近更新：/)
})
