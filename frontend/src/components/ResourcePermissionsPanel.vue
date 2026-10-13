<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Key, Refresh } from '@element-plus/icons-vue'
import type { DocumentCollectionRead, DocumentRead } from '../types'
import { paginateItems } from '../utils/documentList'

const props = defineProps<{
  documents: DocumentRead[]
  collections: DocumentCollectionRead[]
  loading: boolean
}>()
const emit = defineEmits<{
  refresh: []
  authorizeDocument: [document: DocumentRead]
  authorizeCollection: [collection: DocumentCollectionRead]
}>()
const resourceType = ref('collections')
const search = ref('')
const visibleDocuments = computed(() => props.documents.filter((document) =>
  `${document.filename} ${document.collection_name || ''} ${document.owner_username || ''}`
    .toLowerCase().includes(search.value.trim().toLowerCase())
))
const visibleCollections = computed(() => props.collections.filter((collection) =>
  `${collection.name} ${collection.description || ''}`.toLowerCase().includes(search.value.trim().toLowerCase())
))
const documentPage = ref(1)
const documentPageSize = ref(20)
const documentPagination = computed(() => paginateItems(visibleDocuments.value, documentPage.value, documentPageSize.value))
watch(search, () => { documentPage.value = 1 })
watch(documentPageSize, () => { documentPage.value = 1 })
watch(documentPagination, (value) => {
  if (documentPage.value !== value.page) documentPage.value = value.page
})
</script>

<template>
  <section class="resource-permissions">
    <div class="resource-head">
      <p>选择文档集可统一授权其中的文档；单份文档也可以单独授权。</p>
      <el-button :icon="Refresh" :loading="loading" @click="emit('refresh')">刷新资源</el-button>
    </div>
    <el-alert
      type="info"
      show-icon
      :closable="false"
      title="个人、部门与文档集授权共同生效。撤销一条授权后，用户仍可能通过其他授权访问。"
    />
    <div class="resource-filter-toolbar">
      <el-radio-group v-model="resourceType" aria-label="授权资源类型">
        <el-radio-button value="collections">文档集</el-radio-button>
        <el-radio-button value="documents">单份文档</el-radio-button>
      </el-radio-group>
      <el-input v-model="search" clearable aria-label="搜索授权资源" placeholder="搜索资源名称" />
    </div>
    <el-table v-if="resourceType === 'collections'" :data="visibleCollections" v-loading="loading" empty-text="暂无匹配的文档集">
      <el-table-column prop="name" label="文档集" min-width="180" show-overflow-tooltip />
      <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
      <el-table-column prop="document_count" label="文档数" width="90" />
      <el-table-column label="授权" width="120" fixed="right">
        <template #default="{ row }">
          <el-button :icon="Key" size="small" @click="emit('authorizeCollection', row)">管理</el-button>
        </template>
      </el-table-column>
    </el-table>
    <template v-else>
      <el-table :data="documentPagination.items" v-loading="loading" class="resource-document-table" empty-text="暂无匹配的文档">
        <el-table-column prop="filename" label="文档" min-width="240" show-overflow-tooltip />
        <el-table-column label="文档集" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.collection_name || '未分组' }}</template>
        </el-table-column>
        <el-table-column label="上传者" min-width="140">
          <template #default="{ row }">{{ row.owner_username || `用户 ${row.owner_id}` }}</template>
        </el-table-column>
        <el-table-column label="授权" width="140" fixed="right">
          <template #default="{ row }">
            <el-button :icon="Key" @click="emit('authorizeDocument', row)">管理</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="documentPage"
        v-model:page-size="documentPageSize"
        :total="visibleDocuments.length"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        class="resource-document-pagination"
      />
    </template>
  </section>
</template>

<style>
.resource-permissions {
  display: grid;
  gap: 20px;
  min-width: 0;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: 22px 24px 18px;
}

.resource-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.resource-head p {
  margin: 0;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.7;
}

.resource-document-table {
  width: 100%;
}

.resource-document-table .el-table__cell {
  padding-top: 12px;
  padding-bottom: 12px;
}

.resource-document-pagination {
  justify-content: flex-end;
  margin-top: 16px;
  overflow-x: auto;
}
</style>
