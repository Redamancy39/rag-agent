<script setup lang="ts">
import { documentPagination, documentTable, loadingDocuments } from '../../stores/documents'
import { handleDocumentSelectionChange, openPermissions } from '../../stores/permissionActions'
import { currentUser } from '../../auth/session'
import { llmCheckLabel, llmCheckType, llmExecutionNote, llmNormalizationLabel, llmNormalizationType, statusLabel, statusType } from '../../utils/documentStatus'
import { confirmDeleteDocument, openDocumentDetail, triggerChunkNormalization } from '../../stores/documentDialogs'
import { formatTime } from '../../utils/format'
import type { DocumentRead } from '../../types'

function moreActions(row: DocumentRead) {
  const actions: Array<'normalize' | 'permission' | 'delete'> = []
  if (row.status === 'indexed' && row.can_write !== false) actions.push('normalize')
  if (currentUser.value?.is_admin) actions.push('permission', 'delete')
  return actions
}
</script>

<template>
  <el-table
    ref="documentTable"
    :data="documentPagination.items"
    row-key="id"
    v-loading="loadingDocuments"
    class="document-table"
    empty-text="没有符合筛选条件的文档"
    @selection-change="handleDocumentSelectionChange"
  >
    <el-table-column v-if="currentUser?.is_admin" type="selection" width="48" />
    <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip />
    <el-table-column label="状态" width="110">
      <template #default="{ row }">
        <el-tag :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="大模型处理" min-width="220">
      <template #default="{ row }">
        <div class="document-llm-status">
          <el-tooltip :content="row.llm_processing?.detail || '暂无可核验的 LLM 执行记录。'" placement="top">
            <el-tag :type="llmCheckType(row)" size="small" effect="plain">检测 {{ llmCheckLabel(row) }}</el-tag>
          </el-tooltip>
          <el-tag :type="llmNormalizationType(row)" size="small" effect="plain">整理 {{ llmNormalizationLabel(row) }}</el-tag>
          <span>{{ llmExecutionNote(row) }}</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="文档集" min-width="140" show-overflow-tooltip>
      <template #default="{ row }">{{ row.collection_name || '未分组' }}</template>
    </el-table-column>
    <el-table-column label="分块数" width="90">
      <template #default="{ row }">{{ row.chunk_count }}</template>
    </el-table-column>
    <el-table-column label="上传时间" width="170">
      <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="150" fixed="right">
      <template #default="{ row }">
        <el-button size="small" :aria-label="`查看 ${row.filename} 的详情`" @click="openDocumentDetail(row)">详情</el-button>
        <el-dropdown v-if="moreActions(row).length" trigger="click">
          <el-button size="small" :aria-label="`${row.filename} 的更多操作`">更多</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="moreActions(row).includes('normalize')" @click="triggerChunkNormalization(row)">整理</el-dropdown-item>
              <el-dropdown-item v-if="moreActions(row).includes('permission')" @click="openPermissions(row)">权限</el-dropdown-item>
              <el-dropdown-item v-if="moreActions(row).includes('delete')" @click="confirmDeleteDocument(row)">删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </el-table-column>
  </el-table>
</template>
