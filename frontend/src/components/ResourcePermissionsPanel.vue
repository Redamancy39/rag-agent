<script setup lang="ts">
import { computed, ref } from 'vue'
import { Key, Refresh } from '@element-plus/icons-vue'
import type { DocumentCollectionRead, DocumentRead } from '../types'

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
</script>

<template>
  <section class="settings-card">
    <div class="settings-card-head">
      <div>
        <h2>资源授权</h2>
        <p>选择文档集可统一授权其中的文档；单份文档也可以单独授权。</p>
      </div>
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
    <el-table v-else :data="visibleDocuments" v-loading="loading" empty-text="暂无匹配的文档">
      <el-table-column prop="filename" label="文档" min-width="220" show-overflow-tooltip />
      <el-table-column label="文档集" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.collection_name || '未分组' }}</template>
      </el-table-column>
      <el-table-column label="上传者" min-width="120">
        <template #default="{ row }">{{ row.owner_username || `用户 ${row.owner_id}` }}</template>
      </el-table-column>
      <el-table-column label="授权" width="120" fixed="right">
        <template #default="{ row }">
          <el-button :icon="Key" size="small" @click="emit('authorizeDocument', row)">管理</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
