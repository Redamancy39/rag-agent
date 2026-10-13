<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { paginateItems } from '../../utils/documentList'
import { currentUser } from '../../auth/session'
import { documentCollections, documents } from '../../stores/documents'
import { auditLogs, groups, loadingAuditLogs, refreshAuditLogs, users } from '../../stores/permissionAdmin'
import { formatTime } from '../../utils/format'
import { auditActionLabel, auditDetail, auditName } from '../../utils/auditLog'

const userNames = computed(() => new Map(users.value.map((user) => [user.id, user.username])))
const groupNames = computed(() => new Map(groups.value.map((group) => [group.id, group.name])))
const documentNames = computed(() => new Map(documents.value.map((document) => [document.id, document.filename])))
const collectionNames = computed(() => new Map(documentCollections.value.map((collection) => [collection.id, collection.name])))
const auditPage = ref(1)
const auditPageSize = ref(20)
const auditPagination = computed(() => paginateItems(auditLogs.value, auditPage.value, auditPageSize.value))
watch(auditPageSize, () => { auditPage.value = 1 })
watch(auditPagination, (value) => {
  if (auditPage.value !== value.page) auditPage.value = value.page
})
</script>

<template>
  <section v-if="currentUser?.is_admin" class="audit-page">
    <div class="audit-head">
      <p>记录部门、成员、文档集与资源授权的变更。</p>
      <el-button :icon="Refresh" :loading="loadingAuditLogs" @click="refreshAuditLogs">刷新日志</el-button>
    </div>
    <el-table :data="auditPagination.items" v-loading="loadingAuditLogs" class="audit-table" empty-text="暂无权限审计日志">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="动作" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ auditActionLabel(row.action) }}</template>
      </el-table-column>
      <el-table-column label="操作者" min-width="120">
        <template #default="{ row }">{{ auditName(row.actor_user_id, userNames, '用户') }}</template>
      </el-table-column>
      <el-table-column label="文档" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ auditName(row.document_id, documentNames, '文档') }}</template>
      </el-table-column>
      <el-table-column label="用户" min-width="120">
        <template #default="{ row }">{{ auditName(row.user_id, userNames, '用户') }}</template>
      </el-table-column>
      <el-table-column label="部门" min-width="140">
        <template #default="{ row }">{{ auditName(row.group_id, groupNames, '部门') }}</template>
      </el-table-column>
      <el-table-column label="文档集" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ auditName(row.collection_id, collectionNames, '文档集') }}</template>
      </el-table-column>
      <el-table-column label="详情" min-width="240" show-overflow-tooltip>
        <template #default="{ row }">{{ auditDetail(row) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="auditPage"
      v-model:page-size="auditPageSize"
      :total="auditLogs.length"
      :page-sizes="[20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      class="audit-pagination"
    />
  </section>
</template>

<style>
.audit-page {
  display: grid;
  gap: 22px;
  min-width: 0;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: 22px 24px 18px;
}

.audit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.audit-head p {
  margin: 0;
  color: var(--c-64748b);
  font-size: 14px;
  line-height: 1.7;
}

.audit-table {
  width: 100%;
}

.audit-table .el-table__cell {
  padding-top: 12px;
  padding-bottom: 12px;
}

.audit-pagination {
  justify-content: flex-end;
  overflow-x: auto;
}
</style>
