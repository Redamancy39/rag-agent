<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Cloudy } from '@element-plus/icons-vue'
import FolderUploadPanel from '../../components/FolderUploadPanel.vue'
import UploadList from '../../components/upload/UploadList.vue'
import { llmChunkNormalizationMode, llmChunkNormalizationOptions } from '../../stores/uploadForm'
import { documents, failedCount, indexedCount, loadingDocumentCollections, processingCount, selectedUploadCollectionId, writableDocumentCollections } from '../../stores/documents'
import { createFolderUploader, handleUpload } from '../../stores/uploadQueue'

const router = useRouter()
</script>

<template>
      <section class="view-grid">
        <div class="primary-column">
          <section class="upload-panel">
            <div class="panel-heading">
              <div>
                <h2>上传 PDF / Office / Markdown / TXT</h2>
                <p>现代 Office 优先原生解析，旧版或图片密集文档自动回退 LiteParse / OCR。</p>
              </div>
              <el-tag type="info" effect="plain">单文件 50 MB</el-tag>
            </div>

            <div class="upload-options">
              <div>
                <strong>大模型整理 OCR / 表格切块</strong>
                <span>
                  默认仅整理候选切块，前置逐行 LLM 整理关闭。单文档默认最多 120 次请求（含重试）、整理时间预算 10 分钟；达到约束后保留原文。
                </span>
              </div>
              <div class="upload-option-action">
                <el-segmented
                  v-model="llmChunkNormalizationMode"
                  :options="llmChunkNormalizationOptions"
                  class="llm-mode-control"
                />
              </div>
            </div>

            <div class="upload-collection-row">
              <div>
                <strong>所属文档集</strong>
                <span>上传后整份文档会继承文档集权限；不选择则进入“未分组”。</span>
              </div>
              <el-select
                v-model="selectedUploadCollectionId"
                clearable
                filterable
                :loading="loadingDocumentCollections"
                placeholder="未分组"
              >
                <el-option
                  v-for="collection in writableDocumentCollections"
                  :key="collection.id"
                  :label="collection.name"
                  :value="collection.id"
                />
              </el-select>
            </div>

            <FolderUploadPanel :create-uploader="createFolderUploader" />

            <el-upload
              drag
              multiple
              :http-request="handleUpload"
              :show-file-list="false"
              accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md,.markdown,.txt"
              class="upload-drop"
            >
              <el-icon class="upload-icon"><Cloudy /></el-icon>
              <div class="upload-title">拖拽文件到这里，或点击选择文件</div>
              <div class="upload-copy">支持 PDF、DOC/DOCX、PPT/PPTX、XLS/XLSX、Markdown、TXT；旧版 Office 需要后端安装 LibreOffice。</div>
            </el-upload>

            <UploadList />
          </section>
        </div>

        <aside class="inspector">
          <section class="upload-summary">
            <div class="panel-heading">
              <div>
                <h2>当前文档</h2>
                <p>按当前账号可访问的文档统计。</p>
              </div>
            </div>
            <div class="upload-summary-grid">
              <div>
                <span>文档数</span>
                <strong>{{ documents.length }}</strong>
              </div>
              <div>
                <span>已入库</span>
                <strong>{{ indexedCount }}</strong>
              </div>
              <div>
                <span>处理中</span>
                <strong>{{ processingCount }}</strong>
              </div>
              <div>
                <span>失败</span>
                <strong :class="{ 'is-alert': failedCount > 0 }">{{ failedCount }}</strong>
              </div>
            </div>
            <el-button plain @click="router.push({ name: 'documents' })">查看文档列表</el-button>
          </section>
        </aside>
      </section>
</template>

<style>
.inspector {
display: grid;
  gap: 18px;
  min-width: 0;
}

.inspector {
position: sticky;
  top: 20px;
}

.upload-panel,
.upload-summary,
.upload-row {
border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.upload-panel {
min-width: 0;
  padding: 18px;
}

.upload-drop .el-upload {
width: 100%;
}

.upload-options {
display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 12px 14px;
}

.upload-collection-row {
display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 320px);
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 12px 14px;
}

.upload-collection-row > div {
display: grid;
  gap: 4px;
  min-width: 0;
}

.upload-collection-row strong {
color: var(--c-111827);
  font-size: 13px;
}

.upload-collection-row span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
}

.upload-options > div {
display: grid;
  gap: 4px;
  min-width: 0;
}

.upload-option-action {
display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  min-width: 220px;
}

.upload-options > div:first-child > strong {
color: var(--c-111827);
  font-size: 13px;
}

.upload-options > div:first-child > span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
}

.upload-drop .el-upload-dragger {
display: grid;
  min-height: 236px;
  place-items: center;
  align-content: center;
  border: 1px dashed var(--c-99b8b4);
  border-radius: 8px;
  background: var(--c-fbfefd);
  padding: 28px;
}

.upload-icon {
color: var(--c-0f766e);
  font-size: 42px;
}

.upload-title {
margin-top: 10px;
  color: var(--c-111827);
  font-size: 16px;
  font-weight: 720;
}

.upload-copy {
max-width: 560px;
  margin-top: 8px;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.6;
  text-align: center;
}

.upload-list {
display: grid;
  gap: 10px;
  margin-top: 14px;
}

.upload-row {
display: grid;
  gap: 10px;
  padding: 13px 14px;
}

.upload-row-main {
display: grid;
  align-items: center;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 12px;
}

.upload-row-main strong {
min-width: 0;
  overflow: hidden;
  color: var(--c-111827);
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-row-status {
display: grid;
  gap: 4px;
  min-width: 0;
  justify-items: end;
  text-align: right;
}

.upload-row-status span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.45;
}

.upload-row-status small {
color: var(--c-0f766e);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
}

.upload-summary {
padding: 18px;
}

.upload-summary .panel-heading {
margin-bottom: 14px;
}

.upload-summary-grid {
display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 14px;
}

.upload-summary-grid div {
min-width: 0;
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 12px;
}

.upload-summary-grid span {
display: block;
  color: var(--c-64748b);
  font-size: 12px;
}

.upload-summary-grid strong {
display: block;
  margin-top: 6px;
  color: var(--c-111827);
  font-size: 22px;
  font-weight: 760;
}

.upload-summary-grid strong.is-alert {
color: var(--c-dc2626);
}

.upload-summary .el-button {
width: 100%;
}

.upload-stage-waiting {
display: flex;
  align-items: center;
  gap: 8px;
  color: var(--c-0f766e);
  font-size: 12px;
}

@media (max-width: 1320px) {
.inspector {
position: static;
}
}

@media (max-width: 760px) {
.upload-options {
align-items: stretch;
    flex-direction: column;
}
}

@media (max-width: 760px) {
.upload-collection-row {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.upload-option-action {
justify-content: space-between;
    width: 100%;
}
}

@media (max-width: 760px) {
.upload-row-main {
align-items: start;
    grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.upload-row-status {
justify-items: start;
    text-align: left;
}
}
</style>
