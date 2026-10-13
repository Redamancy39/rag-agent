import test from 'node:test'
import assert from 'node:assert/strict'
import {
  answerTextSegments, chatLogToTurn, chatStageLabel, citationLocationLabel, documentNamesForIds,
  normalizeSourceLocation, parseAnswerSections, retrievalSourceLabel
} from '../src/utils/chatResponse.ts'

test('legacy logs recover conclusion and basis instead of the synthetic not-found text', () => {
  const answer = '分类判断：证据匹配\n结论：限量为 0.05 mg/kg[1]\n依据：见表 A.1[1]\n引用：无'
  const turn = chatLogToTurn({
    id: 7, user_id: 1, question: '限量', answer,
    citations_json: null, retrieval_trace: [], query_plan: null, evidence_decision: null,
    citation_validation: { valid: true, cited_indices: [], invalid_indices: [], uncited_sections: [], warnings: [] },
    retrieval_scope: { requested_document_ids: [], allowed_document_ids: [], top_k: 5 },
    response: {
      answer, sections: { classification: '未找到', conclusion: '未找到相关答案。', basis: '未找到可支撑结论的依据。', citation: '无' },
      evidence_rows: [], citations: [], retrieval_trace: [], query_plan: null, evidence_decision: null,
      citation_validation: { valid: true, cited_indices: [], invalid_indices: [], uncited_sections: [], warnings: [] },
      retrieval_scope: { requested_document_ids: [], allowed_document_ids: [], top_k: 5 },
      retrieval_only: false, log_id: 7
    },
    created_at: '2026-10-13T00:00:00Z'
  }, () => undefined)
  assert.equal(turn.response.sections.conclusion, '限量为 0.05 mg/kg[1]')
  assert.equal(turn.response.sections.basis, '见表 A.1[1]')
  assert.deepEqual(parseAnswerSections(answer).classification, '证据匹配')
})

test('citation markers including multi-digit ids stay separate segments', () => {
  assert.deepEqual(answerTextSegments('结论[12]结束'), [
    { text: '结论', citationId: null },
    { text: '[12]', citationId: 12 },
    { text: '结束', citationId: null }
  ])
})

test('plain text stays one segment', () => {
  assert.deepEqual(answerTextSegments('没有引用'), [{ text: '没有引用', citationId: null }])
})

test('history uses the filename lookup when citations have no names', () => {
  const turn = chatLogToTurn({
    id: 1, user_id: 1, question: 'q', answer: 'a', citations_json: null,
    retrieval_trace: [], query_plan: null, evidence_decision: null,
    citation_validation: { valid: true, cited_indices: [], invalid_indices: [], uncited_sections: [], warnings: [] },
    retrieval_scope: { requested_document_ids: [9], allowed_document_ids: [9], top_k: 5 },
    response: null, created_at: '2026-10-13T00:00:00Z'
  }, (id) => id === 9 ? '国标.pdf' : undefined)
  assert.deepEqual(turn.documentNames, ['国标.pdf'])
  assert.equal(turn.documentIds[0], 9)
})

test('document names and retrieval labels have stable fallbacks', () => {
  assert.deepEqual(documentNamesForIds([], () => 'a.txt'), ['全部可访问文档'])
  assert.deepEqual(documentNamesForIds([2], () => undefined), ['文档 2'])
  assert.equal(chatStageLabel('not-a-stage'), '问答任务执行中')
  assert.equal(retrievalSourceLabel('reranked'), 'Reranker 精排')
  assert.equal(retrievalSourceLabel('brand-new'), 'brand-new')
})

test('sheet, slide and page locations keep their labels', () => {
  assert.equal(citationLocationLabel({ sheet: '限量', cell_range: 'B2', page: null, slide: null, section_path: null, paragraph_index: null, location: null }), '工作表 限量 / 单元格 B2')
  assert.equal(citationLocationLabel({ slide: 3, page: null, sheet: null, cell_range: null, section_path: null, paragraph_index: null, location: null }), '第 3 张幻灯片')
  assert.equal(citationLocationLabel({ page: 4, slide: null, sheet: null, cell_range: null, section_path: null, paragraph_index: null, location: null }), '第 4 页')
  const located = normalizeSourceLocation(null, { sheet: '表1', cell_range: 'A1' })
  assert.equal(located.kind, 'sheet')
  assert.match(located.label, /工作表 表1/)
})
