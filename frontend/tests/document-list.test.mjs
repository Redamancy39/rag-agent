import test from 'node:test'
import assert from 'node:assert/strict'
import { filterDocuments, paginateItems } from '../src/utils/documentList.ts'

const filters = { query: '', collection: 'all', llm: 'all', status: 'all', fileType: 'all' }
const documents = [
  { id: 1, filename: 'GB 2760.PDF', collection_id: 1, file_type: 'pdf', status: 'indexed', llm_processing: { check_status: 'completed', normalization_status: 'indexed' } },
  { id: 2, filename: 'GB 2760 草案.docx', collection_id: null, file_type: 'docx', status: 'failed', llm_processing: { check_status: 'not_run' } },
  { id: 3, filename: '指南.txt', collection_id: 2, file_type: 'txt', status: 'queued' },
]
test('name search and every filter combine before pagination', () => {
  const result = filterDocuments(documents, { ...filters, query: '  gb 2760  ', collection: 1, status: 'indexed', fileType: 'pdf', llm: 'normalized' })
  assert.deepEqual(result.map(d => d.id), [1])
  assert.deepEqual(filterDocuments(documents, { ...filters, collection: 'unassigned', status: 'failed' }).map(d => d.id), [2])
  assert.deepEqual(filterDocuments(documents, { ...filters, status: 'processing', llm: 'unknown' }).map(d => d.id), [3])
})
test('pagination reaches beyond 100, clamps after filtering/deletion and handles no matches', () => {
  const items = Array.from({ length: 105 }, (_, i) => i)
  assert.deepEqual(paginateItems(items, 6, 20).items, [100, 101, 102, 103, 104])
  assert.equal(paginateItems(items.slice(0, 3), 6, 20).page, 1)
  assert.deepEqual(paginateItems([], 6, 20), { page: 1, items: [] })
  assert.equal(paginateItems(items, 2, 50).items[0], 50)
})
