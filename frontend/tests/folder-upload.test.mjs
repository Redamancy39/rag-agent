import test from 'node:test'
import assert from 'node:assert/strict'
import { FolderUploadPausedError, MAX_DOCUMENT_BYTES, runFolderFiles, scanFolderFiles } from '../src/utils/folderFiles.ts'

const file = (path, size = 10) => ({ name: path.replaceAll('\\', '/').split('/').at(-1), webkitRelativePath: path, size })

test('nested documents retain paths, uppercase suffixes, and separate same-name files', () => {
  const scan = scanFolderFiles([file('标准/食品/报告.PDF'), file('标准/材料/报告.PDF'), file('标准/说明.md')])
  assert.equal(scan.files.length, 3)
  assert.deepEqual(scan.files.map(f => f.relativePath), ['标准/食品/报告.PDF', '标准/材料/报告.PDF', '标准/说明.md'])
})
test('macOS, Windows, Office and dependency artifacts are skipped before parsing', () => {
  const paths = ['资料/.DS_Store', '资料/__MACOSX/目录/._报告.pdf', '资料/._报告.pdf',
    '资料/Thumbs.db', '资料/Desktop.ini', '资料/.git/说明.txt', '资料/.venv/说明.txt',
    '资料/node_modules/说明.md', '资料/~$报告.docx', '资料/报告.txt~', '资料/备份.pdf.bak']
  const scan = scanFolderFiles(paths.map(path => file(path)))
  assert.equal(scan.files.length, 0)
  assert.equal(scan.skipped.length, paths.length)
  assert.ok(scan.skipped.every(f => f.reason))
})
test('empty, oversized, archive, unsupported and duplicate paths have explicit skip records', () => {
  const scan = scanFolderFiles([file('资料/空.pdf', 0), file('资料/大.pdf', MAX_DOCUMENT_BYTES + 1),
    file('资料/图片.png'), file('资料/文件.zip'), file('资料/报告.txt'), file('资料/报告.txt')])
  assert.equal(scan.files.length, 1)
  assert.equal(scan.skipped.length, 5)
  assert.match(scan.skipped.at(-1).reason, /重复/)
})
test('absolute and traversal paths are rejected while Windows relative separators normalize', () => {
  const scan = scanFolderFiles([file('资料\\子目录\\有效.pdf'), file('../outside.pdf'), file('C:\\outside.pdf'), file('/outside.pdf')])
  assert.equal(scan.files[0].relativePath, '资料/子目录/有效.pdf')
  assert.equal(scan.skipped.length, 3)
})
test('queue waits for completion and continues after a per-file failure', async () => {
  const scan = scanFolderFiles([file('资料/1.txt'), file('资料/2.txt'), file('资料/3.txt')])
  let active = 0, maxActive = 0
  const calls = []
  await runFolderFiles(scan.files, async (_, path) => {
    active++; maxActive = Math.max(maxActive, active); calls.push(path)
    await new Promise(resolve => setTimeout(resolve, 5))
    active--
    if (path.endsWith('2.txt')) throw new Error('synthetic parser failure')
    return 'indexed'
  }, () => false)
  assert.equal(maxActive, 1)
  assert.equal(calls.length, 3)
  assert.deepEqual(scan.files.map(f => f.status), ['indexed', 'failed', 'indexed'])
})
test('stop during accepted task leaves pending files ready; resume does not repeat prior submissions', async () => {
  const scan = scanFolderFiles([file('资料/1.txt'), file('资料/2.txt')])
  let stopped = false
  await runFolderFiles(scan.files, async () => { stopped = true; return 'submitted' }, () => stopped)
  assert.deepEqual(scan.files.map(f => f.status), ['submitted', 'ready'])
  const calls = []
  await runFolderFiles(scan.files, async (_, path) => { calls.push(path); return 'indexed' }, () => false)
  assert.deepEqual(calls, ['资料/2.txt'])
})
test('failed status query preserves accepted task and pauses all later submissions', async () => {
  const scan = scanFolderFiles([file('资料/1.txt'), file('资料/2.txt')])
  let calls = 0
  await runFolderFiles(scan.files, async () => { calls++; throw new FolderUploadPausedError('synthetic disconnect') }, () => false)
  assert.equal(calls, 1)
  assert.deepEqual(scan.files.map(f => f.status), ['submitted', 'ready'])
})

test('unchecked files across preview pages are never submitted, and can be reselected later', async () => {
  const scan = scanFolderFiles(Array.from({ length: 105 }, (_, i) => file(`资料/${i}.txt`)))
  scan.files[0].selected = scan.files[104].selected = false
  const calls = []
  await runFolderFiles(scan.files, async (_, path) => { calls.push(path); return 'indexed' }, () => false)
  assert.equal(calls.length, 103)
  assert.equal(scan.files[0].status, 'ready')
  assert.equal(scan.files[104].status, 'ready')
  scan.files[104].selected = true
  await runFolderFiles(scan.files, async (_, path) => { calls.push(path); return 'duplicate' }, () => false)
  assert.equal(calls.at(-1), '资料/104.txt')
  assert.equal(scan.files[104].status, 'duplicate')
})
