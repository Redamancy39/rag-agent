import test from 'node:test'
import assert from 'node:assert/strict'
import { adoptQuerySuggestion } from '../src/utils/queryAssistance.ts'

test('only adopt a current offered suggestion and preserve surrounding question', () => {
  const original = '😀大肠杆群，GB 4789.3-2016 0.5 mg/kg'
  const suggestion = { start: 1, end: 5, original: '大肠杆群', candidates: ['大肠菌群', '大肠杆菌'] }
  assert.equal(adoptQuerySuggestion(original, original, suggestion, '大肠菌群'), '😀大肠菌群，GB 4789.3-2016 0.5 mg/kg')
  assert.equal(adoptQuerySuggestion(original + '？', original, suggestion, '大肠菌群'), original + '？')
  assert.equal(adoptQuerySuggestion(original, original, suggestion, '沙门氏菌'), original)
  assert.equal(adoptQuerySuggestion(original, original, {...suggestion, start: 0}, '大肠菌群'), original)
})
