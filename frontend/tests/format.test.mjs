import test from 'node:test'
import assert from 'node:assert/strict'
import { formatFileSize, formatJson, formatPercentScore, formatScore, textPreview } from '../src/utils/format.ts'

test('zero bytes stay in bytes', () => {
  assert.equal(formatFileSize(0), '0 B')
})

test('empty and short text is not truncated', () => {
  assert.equal(textPreview(''), '')
  assert.equal(textPreview('abc', 3), 'abc')
  assert.equal(formatPercentScore(Number.NaN), '-')
  assert.equal(formatScore(1), '1.000')
  assert.equal(formatFileSize(1024 * 1024), '1.0 MB')
  assert.equal(formatJson({}), '{}')
})

test('file size, score and preview stay bounded', () => {
  assert.equal(formatFileSize(512), '512 B')
  assert.equal(formatFileSize(2048), '2.0 KB')
  assert.equal(formatPercentScore(0.126), '13%')
  assert.equal(formatPercentScore(null), '-')
  assert.equal(formatScore(null), '-')
  assert.equal(formatScore(0.5), '0.500')
  assert.equal(textPreview('abcd', 3), 'abc\n...')
  assert.equal(formatJson(null), '-')
  assert.equal(formatJson({ a: 1 }), '{\n  "a": 1\n}')
})
