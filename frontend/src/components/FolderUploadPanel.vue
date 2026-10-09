<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FolderOpened } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { runFolderFiles, scanFolderFiles, type FolderScan, type FolderUploader } from '../utils/folderFiles'
import { paginateItems } from '../utils/documentList'

const props = defineProps<{ createUploader: () => FolderUploader }>()
const picker = ref<HTMLInputElement>()
const scan = ref<FolderScan | null>(null)
const running = ref(false)
const stopping = ref(false)
const previewPage = ref(1)
const previewPageSize = ref(20)
const previewQuery = ref('')
const previewFiles = computed(() => {
  const query = previewQuery.value.trim().toLocaleLowerCase()
  return (scan.value?.files || []).filter(file => !query || file.relativePath.toLocaleLowerCase().includes(query))
})
const preview = computed(() => paginateItems(previewFiles.value, previewPage.value, previewPageSize.value))
watch([previewQuery, previewPageSize], () => { previewPage.value = 1 })
const directorySupported = 'webkitdirectory' in document.createElement('input')
const pending = computed(() => scan.value?.files.filter(file => file.status === 'ready' && file.selected).length || 0)
const excluded = computed(() => scan.value?.files.filter(file => file.status === 'ready' && !file.selected).length || 0)
const duplicates = computed(() => scan.value?.files.filter(file => file.status === 'duplicate').length || 0)
const indexed = computed(() => scan.value?.files.filter(file => file.status === 'indexed').length || 0)
const submitted = computed(() => scan.value?.files.filter(file => file.status === 'submitted').length || 0)
const failed = computed(() => scan.value?.files.filter(file => file.status === 'failed').length || 0)
const working = computed(() => scan.value?.files.find(file => file.status === 'working')?.relativePath)
const name = computed(() => (scan.value?.files[0]?.relativePath || scan.value?.skipped[0]?.relativePath || '').split('/')[0])
const labels = { ready: '待上传', working: '上传 / 后台处理中', indexed: '入库完成', submitted: '已提交，后台继续', failed: '失败', duplicate: '重复内容，已跳过' }

function selectPending(selected: boolean) {
  if (running.value) return
  for (const file of scan.value?.files || []) if (file.status === 'ready') file.selected = selected
}

function selectFolder(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) scan.value = scanFolderFiles(Array.from(input.files))
  input.value = ''
  stopping.value = false
  previewPage.value = 1
  previewQuery.value = ''
}
async function start() {
  if (!scan.value || running.value || !pending.value) return
  const upload = props.createUploader()
  stopping.value = false
  running.value = true
  try {
    await runFolderFiles(scan.value.files, upload, () => stopping.value)
    if (stopping.value) ElMessage.info('已停止后续上传，已提交的任务仍在后台处理')
    else if (pending.value) ElMessage.warning('查询中断，本批已暂停；请恢复连接后查看文档列表，再继续上传')
  } finally { running.value = false }
}
onBeforeUnmount(() => { stopping.value = true })
defineExpose({ running, stopping, pending, working })
</script>

<template>
  <section class="folder-import" aria-label="递归上传文件夹">
    <div class="folder-import-heading">
      <div>
        <strong>上传文件夹</strong>
        <p>包含所有子文件夹，先筛选再上传；自动跳过系统元数据、隐藏文件、临时文件和不支持的格式。</p>
      </div>
      <el-button :icon="FolderOpened" :disabled="running || !directorySupported" @click="picker?.click()">选择文件夹</el-button>
      <input ref="picker" type="file" webkitdirectory multiple hidden aria-label="选择包含文档的文件夹" @change="selectFolder" />
    </div>
    <p v-if="!directorySupported" class="folder-import-note">当前浏览器不支持文件夹选择，请使用下方的单文件上传。</p>
    <template v-if="scan">
      <div class="folder-import-summary" aria-live="polite">
        <strong>{{ name || '所选文件夹' }}</strong>
        <span>扫描 {{ scan.total }} 个文件 · 有效 {{ scan.files.length }} · 跳过 {{ scan.skipped.length }}</span>
        <span>选中待上传 {{ pending }} · 手动排除 {{ excluded }} · 重复跳过 {{ duplicates }}</span>
        <span v-if="indexed || failed || submitted">入库完成 {{ indexed }} · 失败 {{ failed }} · 已提交仍处理中 {{ submitted }}</span>
        <span v-if="working" class="folder-current-path">当前：{{ working }}</span>
      </div>
      <details v-if="scan.files.length" class="folder-import-details" open>
        <summary>查看有效文件与处理结果（{{ scan.files.length }}）</summary>
        <div class="folder-preview-tools">
          <el-input v-model="previewQuery" aria-label="搜索预览文件路径" placeholder="搜索文件名或相对路径" clearable />
          <el-button :disabled="running" @click="selectPending(true)">全选待上传</el-button>
          <el-button :disabled="running" @click="selectPending(false)">取消全部待上传</el-button>
        </div>
        <ul>
          <li v-for="file in preview.items" :key="file.relativePath">
            <el-checkbox v-model="file.selected" :disabled="running || file.status !== 'ready'" :aria-label="`上传 ${file.relativePath}`" />
            <span :title="file.relativePath">{{ file.relativePath }}</span><span>{{ file.error || (file.status === 'ready' && !file.selected ? '本批不上传' : labels[file.status]) }}</span>
          </li>
        </ul>
        <p v-if="!previewFiles.length">没有匹配的有效文件。</p>
        <el-pagination v-model:current-page="previewPage" v-model:page-size="previewPageSize" :total="previewFiles.length" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next" small />
        <p>搜索只改变预览结果；上传全部已勾选的待上传文件。全选和取消全部作用于所有待上传文件。</p>
      </details>
      <details v-if="scan.skipped.length" class="folder-import-details">
        <summary>查看跳过原因（{{ scan.skipped.length }}）</summary>
        <ul><li v-for="(file, index) in scan.skipped.slice(0, 100)" :key="index" class="skipped-file"><span :title="file.relativePath">{{ file.relativePath }}</span><span>{{ file.reason }}</span></li></ul>
        <p v-if="scan.skipped.length > 100">仅展示前 100 条跳过记录。</p>
      </details>
      <p class="folder-import-note">仅上传勾选文件，逐份等待处理结果；失败后继续下一份。同一上传者、同一文档集内的完全相同内容会跳过重复入库，与文件名无关。压缩包请先解压。</p>
      <p class="folder-import-note">本批固定使用开始时选择的文档集和大模型整理设置；启用整理可能发送候选内容到 DeepSeek 并产生费用。站内切换页面会继续上传；刷新、关闭浏览器或退出登录会停止尚未提交的文件。</p>
      <div class="folder-import-actions">
        <el-button type="primary" :disabled="running || !pending" @click="start">{{ indexed || failed || submitted ? '继续上传' : '开始上传' }} {{ pending }} 个文件</el-button>
        <el-button v-if="running" :disabled="stopping" @click="stopping = true">{{ stopping ? '正在停止后续上传' : '停止后续上传' }}</el-button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.folder-import { margin-bottom: 16px; padding: 16px; border: 1px solid #dce3ea; border-radius: 8px; background: #f8fafc; }
.folder-import-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.folder-import-heading > div { min-width: 0; }
.folder-import-heading strong, .folder-import-summary strong { color: #111827; font-size: 14px; }
.folder-import-heading p, .folder-import-note, .folder-import-details p { margin: 6px 0; color: #64748b; font-size: 12px; line-height: 1.6; }
.folder-import-summary { display: grid; gap: 6px; margin-top: 14px; color: #0f766e; font-size: 12px; }
.folder-current-path { overflow-wrap: anywhere; }
.folder-import-details { margin-top: 12px; font-size: 12px; color: #475569; }
.folder-import-details summary { cursor: pointer; padding: 6px 0; }
.folder-import-details ul { max-height: 240px; overflow: auto; margin: 6px 0 10px; padding: 0; list-style: none; }
.folder-import-details li { display: grid; grid-template-columns: 24px minmax(0, 1fr) minmax(110px, 30%); align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #e2e8f0; }
.folder-import-details li.skipped-file { grid-template-columns: minmax(0, 1fr) minmax(110px, 30%); }
.folder-preview-tools { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.folder-preview-tools .el-input { width: min(300px, 100%); }
.folder-import-details .el-pagination { overflow-x: auto; padding: 6px 0; }
.folder-import-details li span { overflow-wrap: anywhere; }
.folder-import-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.folder-import-actions .el-button { margin-left: 0; }
@media (max-width: 640px) { .folder-import-heading { align-items: stretch; flex-direction: column; } .folder-import-details li { grid-template-columns: 24px minmax(0, 1fr); gap: 4px; } .folder-import-details li > span:last-child { grid-column: 2; } }
</style>
