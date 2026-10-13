<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { currentUser, token } from '../../auth/session'
import { getApiBaseUrl, getSystemInfo } from '../../api/client'
import type { SystemInfo } from '../../types'
import { backendOnline } from '../../stores/system'
import { documents, indexedCount, processingCount, refreshDocuments, totalChunkCount, totalFileSize } from '../../stores/documents'
import { llmChunkNormalizationMode } from '../../stores/uploadForm'
import { llmChunkNormalizationModeLabel } from '../../utils/documentStatus'
import { formatFileSize } from '../../utils/format'

const demoOverviewCards = computed(() => [
  { label: '可访问文档', value: documents.value.length, note: '按登录用户权限过滤' },
  { label: '已入库文档', value: indexedCount.value, note: '可参与 RAG 检索' },
  { label: '总切块数', value: totalChunkCount.value, note: '含页码与来源 metadata' },
  { label: '处理中', value: processingCount.value, note: '队列 / OCR / LLM / Embedding' }
])
const ragPipelineStages = [
  { title: '1. Ingestion Agent 探测', detail: '识别 PDF、Office 文档的可读性、表格密度与原生/LiteParse/OCR 处理策略。' },
  { title: '2. 解析与预处理', detail: 'PDF 使用 PyMuPDF / OCR，Office 文档提取标题、正文、表格和来源定位。' },
  { title: '3. 表格与切块质量增强', detail: '表格行转事实文本，低质量 OCR / 表格块可由 LLM 归一化。' },
  { title: '4. 向量化与混合检索', detail: 'BGE Embedding 写入 ChromaDB，问答阶段融合向量、BM25、关键词和 Reranker。' },
  { title: '5. 权限感知问答', detail: '后端计算可访问文档范围，证据不足时返回未找到，并记录日志。' }
]
const capabilityCards = [
  { title: '权限控制', value: '用户、部门与文档集授权', status: '已接入' },
  { title: '文档入库', value: 'PDF / 新旧 Office / Markdown / TXT', status: '已接入' },
  { title: '检索增强', value: '向量 + BM25 + 关键词 + Reranker', status: '已接入' },
  { title: '问答', value: '按问题决定是否查库，查中后走混合检索与证据判断', status: '已接入' },
  { title: '可观测性', value: '任务表、质量报告、审计日志', status: '已接入' },
  { title: '评测题库', value: '仓库保留 500 条领域评测题', status: '已接入' }
]
const systemInfo = ref<SystemInfo | null>(null)
const llmSummary = computed(() => {
  if (!systemInfo.value) return '默认配置，实际以后端配置为准'
  if (systemInfo.value.llm_mode === 'offline') return '离线（不调用大模型）'
  return systemInfo.value.llm_model || systemInfo.value.llm_mode
})
const rerankerSummary = computed(() => {
  if (!systemInfo.value) return '默认配置，实际以后端配置为准'
  return systemInfo.value.reranker_enabled ? (systemInfo.value.reranker_model || '已开启') : '关闭'
})
onMounted(async () => {
  void refreshDocuments()
  if (!token.value) return
  try { systemInfo.value = await getSystemInfo(token.value) } catch { systemInfo.value = null }
})
</script>

<template>
  <section class="settings-page">
    <section class="settings-card settings-card-wide demo-overview-card">
      <div class="settings-card-head">
        <div>
          <h2>运行概览</h2>
          <p>当前账号可访问的文档、切块和处理中任务。</p>
        </div>
        <el-tag type="success" effect="plain">知识库</el-tag>
      </div>
      <div class="demo-metric-grid">
        <div v-for="card in demoOverviewCards" :key="card.label" class="demo-metric">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.note }}</small>
        </div>
        <div class="demo-metric">
          <span>文件体量</span>
          <strong>{{ formatFileSize(totalFileSize) }}</strong>
          <small>本地 data/uploads 管理原文</small>
        </div>
      </div>
      <div class="pipeline-strip">
        <div v-for="(stage, index) in ragPipelineStages" :key="stage.title" class="pipeline-step">
          <div class="pipeline-index">{{ index + 1 }}</div>
          <strong>{{ stage.title }}</strong>
          <p>{{ stage.detail }}</p>
        </div>
      </div>
    </section>
    <section class="settings-card settings-card-wide">
      <div class="settings-card-head"><div><h2>能力矩阵</h2><p>当前已经接入的能力。</p></div></div>
      <div class="capability-grid">
        <div v-for="item in capabilityCards" :key="item.title" class="capability-card">
          <div><strong>{{ item.title }}</strong><el-tag size="small" effect="plain">{{ item.status }}</el-tag></div>
          <p>{{ item.value }}</p>
        </div>
      </div>
    </section>
    <section class="settings-card">
      <div class="settings-card-head">
        <div><h2>模型与服务</h2><p>默认配置，实际以后端配置为准。</p></div>
        <el-tag :type="backendOnline ? 'success' : 'danger'" effect="plain">{{ backendOnline ? '后端在线' : '后端离线' }}</el-tag>
      </div>
      <div class="settings-kv-grid">
        <div><span>LLM</span><strong>{{ llmSummary }}</strong></div>
        <div><span>Embedding</span><strong>{{ systemInfo?.embedding_model || '默认配置，实际以后端配置为准' }}</strong></div>
        <div><span>Reranker</span><strong>{{ rerankerSummary }}</strong></div>
        <div><span>向量库</span><strong>ChromaDB</strong></div>
        <div><span>后端地址</span><strong>{{ getApiBaseUrl() }}</strong></div>
      </div>
    </section>
    <section class="settings-card">
      <div class="settings-card-head"><div><h2>RAG 检索策略</h2><p>问答参数在知识问答页按账号保存在本浏览器。</p></div></div>
      <div class="settings-list">
        <div><strong>召回与重排</strong><span>Top-K、最低相似度阈值、Reranker 开关、重排保留数量。</span></div>
        <div><strong>证据约束</strong><span>无证据时返回“未找到”，引用页码、文件名、块 ID 必须随答案返回。</span></div>
        <div><strong>问答日志</strong><span>按用户保存问题、答案、引用来源，支持后续审计和效果回放。</span></div>
      </div>
    </section>
    <section class="settings-card">
      <div class="settings-card-head"><div><h2>文档处理策略</h2><p>上传页控制开关会影响本次入库任务，不会强制重处理历史文档。</p></div></div>
      <div class="settings-list">
        <div><strong>PDF 探测</strong><span>先判断是否能直接读取正文和表格，失败或质量低时再进入 OCR。</span></div>
        <div><strong>OCR 处理</strong><span>使用 PaddleOCR，记录页码、行置信度和 OCR 来源类型。</span></div>
        <div><strong>LLM 切块整理</strong><span>当前上传策略为 {{ llmChunkNormalizationModeLabel(llmChunkNormalizationMode) }}；推荐使用自动判断，仅在质量策略命中时调用 LLM。</span></div>
      </div>
    </section>
    <section class="settings-card">
      <div class="settings-card-head">
        <div><h2>权限与数据</h2><p>权限必须在后端和检索阶段生效，不能只依赖前端隐藏。</p></div>
        <el-tag :type="currentUser?.is_admin ? 'success' : 'info'" effect="plain">{{ currentUser?.is_admin ? '管理员视图' : '普通用户视图' }}</el-tag>
      </div>
      <div class="settings-list">
        <div><strong>用户与角色</strong><span>管理员删除文档、查看任务；普通用户只能访问自己有权限的文档。</span></div>
        <div><strong>文件存储</strong><span>原始文件保存到 data/uploads，向量数据保存到 data/chroma，日志保存到 data/logs。</span></div>
        <div><strong>后续可编辑项</strong><span>模型路径、OCR 设备、RAG 阈值、任务并发和日志保留周期；当前为只读展示。</span></div>
      </div>
    </section>
  </section>
</template>

<style>
.settings-card {
border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.settings-card {
min-width: 0;
  padding: 18px;
}

.settings-page {
display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.settings-card {
display: grid;
  align-content: start;
  gap: 16px;
}

.settings-card-head {
display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.settings-card h2 {
margin: 0;
  color: var(--c-111827);
  font-size: 16px;
  font-weight: 740;
  letter-spacing: 0;
}

.settings-card p {
margin: 7px 0 0;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.55;
}

.settings-kv-grid {
display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.settings-kv-grid div,
.settings-list div {
display: grid;
  gap: 5px;
  min-width: 0;
  border-radius: 6px;
  background: var(--c-f8fafc);
  padding: 11px 12px;
}

.settings-kv-grid span,
.settings-list span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.45;
}

.settings-kv-grid strong,
.settings-list strong {
overflow-wrap: anywhere;
  color: var(--c-111827);
  font-size: 13px;
  font-weight: 720;
  line-height: 1.45;
}

.settings-list {
display: grid;
  gap: 10px;
}

.settings-card-wide {
grid-column: 1 / -1;
}

.demo-overview-card {
background:
    linear-gradient(180deg, rgba(15, 118, 110, 0.06), rgba(255, 255, 255, 0) 42%),
    var(--c-ffffff);
}

.demo-metric-grid {
display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.demo-metric {
display: grid;
  gap: 6px;
  min-width: 0;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  padding: 13px 14px;
}

.demo-metric span,
.demo-metric small {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.45;
}

.demo-metric strong {
overflow-wrap: anywhere;
  color: var(--c-111827);
  font-size: 23px;
  font-weight: 780;
  line-height: 1.1;
}

.pipeline-strip {
display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  overflow: hidden;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
}

.pipeline-step {
display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
  border-right: 1px solid var(--c-e2e8f0);
  padding: 14px;
}

.pipeline-step:last-child {
border-right: 0;
}

.pipeline-index {
display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 999px;
  background: var(--c-0f766e);
  color: var(--c-ffffff);
  font-size: 12px;
  font-weight: 760;
}

.pipeline-step strong {
color: var(--c-111827);
  font-size: 13px;
  line-height: 1.45;
}

.pipeline-step p {
margin: 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.55;
}

.capability-grid {
display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.capability-card {
display: grid;
  gap: 8px;
  min-width: 0;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 12px;
}

.capability-card div {
display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.capability-card strong {
color: var(--c-111827);
  font-size: 13px;
  font-weight: 740;
}

.capability-card p {
margin: 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.55;
}

@media (max-width: 1320px) {
.settings-page {
grid-template-columns: 1fr;
}
}

@media (max-width: 1320px) {
.demo-metric-grid,
.pipeline-strip,
.capability-grid {
grid-template-columns: repeat(2, minmax(0, 1fr));
}
}

@media (max-width: 1320px) {
.pipeline-step {
border-right: 0;
    border-bottom: 1px solid var(--c-e2e8f0);
}
}

@media (max-width: 1320px) {
.pipeline-step:nth-last-child(-n + 2) {
border-bottom: 0;
}
}

@media (max-width: 760px) {
.demo-metric-grid,
.pipeline-strip,
.capability-grid,
.settings-kv-grid {
grid-template-columns: 1fr;
}
}
</style>
