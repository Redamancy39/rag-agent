import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_RETRIEVAL, loadRetrievalPreferences, saveRetrievalPreferences,
  resolvedCandidateCount, resolvedContextChars, sanitizeRetrieval } from '../src/utils/retrievalPreferences.ts'

test('Top-K 40 updates auto candidate and context budgets, preserving manual settings', () => {
  const prefs = sanitizeRetrieval({ ...DEFAULT_RETRIEVAL, top_k: 40 })
  assert.equal(resolvedCandidateCount(prefs), 80)
  assert.equal(resolvedContextChars(prefs), 48000)
  const manual = sanitizeRetrieval({ ...prefs, candidate_top_k: 16, context_auto: false, context_max_chars: 64000 })
  assert.equal(resolvedCandidateCount(manual), 40)
  assert.equal(resolvedContextChars(manual), 64000)
})
test('invalid persisted input is bounded or restored, never NaN or excessive budgets', () => {
  const prefs = sanitizeRetrieval({ top_k: 1000, candidate_top_k: 3000, context_max_chars: NaN })
  assert.equal(prefs.top_k, 40); assert.equal(prefs.candidate_top_k, 128); assert.equal(prefs.context_max_chars, 16000)
  assert.deepEqual(sanitizeRetrieval(null), DEFAULT_RETRIEVAL)
})
test('preferences restore independently per account and corrupted storage falls back', () => {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  saveRetrievalPreferences(storage, 1, { ...DEFAULT_RETRIEVAL, top_k: 40 })
  saveRetrievalPreferences(storage, 2, { ...DEFAULT_RETRIEVAL, top_k: 10, rerank_enabled: false })
  assert.equal(loadRetrievalPreferences(storage, 1).top_k, 40)
  assert.equal(loadRetrievalPreferences(storage, 2).top_k, 10)
  assert.equal(loadRetrievalPreferences(storage, 2).rerank_enabled, false)
  assert.equal(loadRetrievalPreferences({ getItem: () => 'broken' }, 1).top_k, 5)
})
test('request snapshot remains unchanged when live settings move and storage is restricted', () => {
  const current = { ...DEFAULT_RETRIEVAL, top_k: 20 }
  const snapshot = sanitizeRetrieval(current)
  current.top_k = 40
  assert.equal(snapshot.top_k, 20)
  assert.doesNotThrow(() => saveRetrievalPreferences({ setItem: () => { throw new Error('restricted') } }, 1, snapshot))
})
