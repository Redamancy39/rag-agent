<script setup lang="ts">
import { Refresh, UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import PermissionGrantDialog from '../../components/permissions/PermissionGrantDialog.vue'
import DocumentFilters from '../../components/documents/DocumentFilters.vue'
import DocumentTable from '../../components/documents/DocumentTable.vue'
import DocumentDetailDrawer from '../../components/documents/DocumentDetailDrawer.vue'
import { documentCollections, documentPage, documentPageSize, filteredDocuments, loadingDocuments, moveTargetCollectionId, refreshDocuments, selectedDocumentRows } from '../../stores/documents'
import { currentUser } from '../../auth/session'
import { grantDocumentGroup, grantDocumentUser, moveSelectedDocuments, revokeGroupPermission, revokePermission } from '../../stores/permissionActions'
import { groups, loadingPermissions, permissionDialogTitle, permissionDialogVisible, permissionUserOptions, selectedGroupPermissions, selectedPermissions } from '../../stores/permissionAdmin'
const router = useRouter()
</script>

<template>
<section class="document-panel">
          <div class="panel-heading">
            <div>
              <h2>文档列表</h2>
              <p>状态为 indexed 才代表已经写入向量库。管理员可以删除文档和对应向量。</p>
            </div>
            <div class="panel-actions">
              <el-button :icon="UploadFilled" @click="router.push({ name: 'upload' })">上传文档</el-button>
              <el-button :icon="Refresh" :loading="loadingDocuments" @click="refreshDocuments">刷新列表</el-button>
            </div>
          </div>
          <DocumentFilters />
          <div v-if="currentUser?.is_admin" class="document-batch-toolbar">
            <span>本页已选择 {{ selectedDocumentRows.length }} 个文档</span>
            <el-select
              v-model="moveTargetCollectionId"
              filterable
              placeholder="选择目标文档集"
            >
              <el-option label="未分组" value="unassigned" />
              <el-option
                v-for="collection in documentCollections"
                :key="collection.id"
                :label="collection.name"
                :value="collection.id"
              />
            </el-select>
            <el-button
              type="primary"
              plain
              :disabled="!selectedDocumentRows.length || moveTargetCollectionId === null"
              @click="moveSelectedDocuments"
            >
              批量移动
            </el-button>
          </div>
          <div class="table-wrap">
            <DocumentTable />
          </div>
          <el-pagination v-model:current-page="documentPage" v-model:page-size="documentPageSize" :total="filteredDocuments.length" :page-sizes="[20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" class="document-pagination" />
        </section>
        <DocumentDetailDrawer />

<PermissionGrantDialog
  v-model="permissionDialogVisible"
  :title="permissionDialogTitle"
  alert="权限在后端文档列表和 RAG 检索阶段都会生效。文档上传者默认拥有访问权限，不需要单独授权。"
  :loading="loadingPermissions"
  detailed
  :users="permissionUserOptions"
  :groups="groups"
  :user-grants="selectedPermissions"
  :group-grants="selectedGroupPermissions"
  :grant-user="grantDocumentUser"
  :grant-group="grantDocumentGroup"
  :revoke-user="revokePermission"
  :revoke-group="revokeGroupPermission"
  group-hint="适合把同一批文档开放给法规部、研发部等用户组。"
/>
</template>

<style>
.document-panel {
border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.document-panel {
min-width: 0;
  padding: 18px;
}

.table-wrap {
min-width: 0;
  overflow: hidden;
}

.document-batch-toolbar {
display: grid;
  grid-template-columns: minmax(140px, 1fr) minmax(220px, 320px) auto;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 10px 12px;
}

.document-batch-toolbar > span {
color: var(--c-475569);
  font-size: 13px;
  font-weight: 650;
}

.document-table {
--el-table-header-bg-color: var(--c-f8fafc);
  --el-table-header-text-color: var(--c-475569);
  width: 100%;
  min-width: 0;
  border-radius: 6px;
  overflow: hidden;
}

.document-table .el-scrollbar__bar.is-horizontal {
height: 10px;
}

.document-table .el-scrollbar__thumb {
background-color: var(--c-94a3b8);
}

.chunk-dialog-body {
min-height: 240px;
}

.chunk-list {
display: grid;
  gap: 12px;
  max-height: 60vh;
  margin-top: 14px;
  overflow: auto;
  padding-right: 4px;
}

.chunk-card {
border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  padding: 14px;
}

.chunk-card header {
display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.chunk-card header div {
display: grid;
  gap: 3px;
  min-width: 0;
}

.chunk-card header .chunk-tags {
display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  min-width: 220px;
}

.chunk-card header strong {
overflow: hidden;
  color: var(--c-111827);
  font-size: 13px;
  font-weight: 730;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chunk-card header span {
color: var(--c-64748b);
  font-size: 12px;
}

.chunk-quality-row {
display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 10px;
  color: var(--c-64748b);
  font-size: 12px;
}

.chunk-card p {
margin: 0;
  color: var(--c-1f2937);
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.document-filter-toolbar {
display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.document-filter-toolbar {
margin-bottom: 16px;
  color: var(--c-475569);
  font-size: 13px;
}

.document-filter-toolbar .el-select {
width: 240px;
}

.document-filter-toolbar .document-name-search {
width: min(280px, 100%);
}

.document-filter-toolbar .document-state-filter {
width: 160px;
}

.document-filter-field {
display: flex; align-items: center; gap: 8px;
}

.document-filter-field label {
white-space: nowrap;
}

.document-pagination {
margin-top: 16px; overflow-x: auto;
}

.document-llm-status {
display: grid;
  justify-items: start;
  gap: 5px;
}

.document-filter-toolbar .llm-status-filter {
width: 208px;
}

.document-llm-status > span {
color: var(--c-64748b);
  font-size: 11px;
  line-height: 1.4;
}

.document-llm-details {
border: 0;
  padding: 0;
  color: var(--c-0f766e);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
}

.document-llm-details:hover {
text-decoration: underline;
}

.document-llm-overview {
display: grid;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 6px;
  background: var(--c-f7faf9);
}

.document-llm-overview p {
margin: 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.6;
}

.job-dialog-body {
display: grid;
  gap: 16px;
}

.quality-report-body {
display: grid;
  gap: 16px;
}

.quality-summary-grid {
display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.quality-summary-grid div,
.quality-section {
border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 12px;
}

.quality-summary-grid span {
display: block;
  color: var(--c-64748b);
  font-size: 12px;
}

.quality-summary-grid strong {
display: block;
  margin-top: 6px;
  color: var(--c-111827);
  font-size: 22px;
  font-weight: 760;
}

.quality-score-card {
background: var(--c-f0fdfa) !important;
}

.quality-section {
display: grid;
  gap: 10px;
}

.quality-section h3 {
margin: 0;
  color: var(--c-111827);
  font-size: 14px;
  font-weight: 740;
}

.quality-section p {
margin: 0;
  color: var(--c-475569);
  font-size: 13px;
  line-height: 1.55;
}

.quality-pill-grid {
display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quality-pill-grid span {
border-radius: 6px;
  background: var(--c-ffffff);
  color: var(--c-334155);
  font-size: 12px;
  font-weight: 650;
  padding: 6px 8px;
}

.quality-risk-grid {
margin-bottom: 2px;
}

.quality-stage-list {
display: grid;
  gap: 10px;
}

.quality-stage-item {
display: grid;
  grid-template-columns: 68px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  border-radius: 8px;
  background: var(--c-ffffff);
  padding: 10px;
}

.quality-stage-item strong {
display: block;
  color: var(--c-111827);
  font-size: 13px;
  font-weight: 740;
}

.quality-stage-item p,
.quality-stage-item small {
display: block;
  margin: 4px 0 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
}

.quality-recommendations {
display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
}

.quality-recommendations li {
color: var(--c-334155);
  font-size: 13px;
  line-height: 1.55;
}

.job-detail-collapse {
border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  overflow: hidden;
}

.job-trace-section {
display: grid;
  gap: 12px;
  margin-bottom: 16px;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 14px;
}

.job-trace-head {
display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.job-trace-head h3 {
margin: 0;
  color: var(--c-0f172a);
  font-size: 14px;
  font-weight: 760;
}

.job-trace-head span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.5;
  text-align: right;
}

.job-trace-timeline {
padding: 4px 0 0;
}

.job-trace-timeline.compact {
padding-top: 8px;
}

.job-trace-card {
display: grid;
  gap: 6px;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-ffffff);
  padding: 10px;
}

.job-trace-title {
display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.job-trace-title strong {
color: var(--c-111827);
  font-size: 13px;
  font-weight: 760;
}

.job-trace-card p {
margin: 0;
  color: var(--c-475569);
  font-size: 12px;
  line-height: 1.5;
}

.job-trace-error {
color: var(--c-dc2626) !important;
}

.job-trace-summary {
display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.job-trace-summary span {
border-radius: 6px;
  background: var(--c-ecfeff);
  color: var(--c-0f766e);
  font-size: 12px;
  font-weight: 650;
  padding: 4px 6px;
}

.job-detail-grid {
display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.job-detail-grid h3 {
margin: 0 0 8px;
  color: var(--c-0f172a);
  font-size: 13px;
}

@media (max-width: 760px) {
.document-batch-toolbar {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.job-detail-grid,
.quality-summary-grid {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.quality-stage-item {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.job-trace-head {
display: grid;
}
}

@media (max-width: 760px) {
.job-trace-head span {
text-align: left;
}
}
</style>
