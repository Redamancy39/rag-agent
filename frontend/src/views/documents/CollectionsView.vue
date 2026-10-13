<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Key, Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { paginateItems } from '../../utils/documentList'
import PermissionGrantDialog from '../../components/permissions/PermissionGrantDialog.vue'
import { documentCollectionFilter, documentCollections, loadingDocumentCollections, refreshDocumentCollections, selectedCollection } from '../../stores/documents'
import { currentUser } from '../../auth/session'
import { collectionPermissionDialogVisible, collectionPermissionUserOptions, documentCollectionForm, groups, loadingPermissions, selectedCollectionGroupPermissions, selectedCollectionUserPermissions } from '../../stores/permissionAdmin'
import { grantCollectionGroup, grantCollectionUser, openCollectionPermissions, removeDocumentCollection, revokeCollectionGroupPermission, revokeCollectionUserPermission, submitDocumentCollection } from '../../stores/permissionActions'
import { formatTime } from '../../utils/format'
const router = useRouter()
const collectionPage = ref(1)
const collectionPageSize = ref(20)
const collectionPagination = computed(() => paginateItems(documentCollections.value, collectionPage.value, collectionPageSize.value))
watch(collectionPagination, (value) => {
  if (collectionPage.value !== value.page) collectionPage.value = value.page
})
watch(collectionPageSize, () => { collectionPage.value = 1 })
function showCollectionDocuments(row: { id: number }) {
  documentCollectionFilter.value = row.id
  void router.push({ name: 'documents' })
}
</script>

<template>
        <section class="collection-page">
          <div class="collection-head">
            <div>
              <h2>文档集管理</h2>
              <p>文档只能归属一个文档集。文档集授权对其中所有文档生效，并与单份文档授权共同决定访问范围。</p>
            </div>
            <el-button
              :icon="Refresh"
              :loading="loadingDocumentCollections"
              @click="refreshDocumentCollections"
            >
              刷新
            </el-button>
          </div>

          <section v-if="currentUser?.is_admin" class="collection-create">
            <el-input aria-label="文档集名称" v-model="documentCollectionForm.name" placeholder="文档集名称，例如：食品安全国标" />
            <el-input aria-label="文档集说明" v-model="documentCollectionForm.description" placeholder="文档集说明，可选" />
            <el-button
              type="primary"
              :loading="loadingDocumentCollections"
              @click="submitDocumentCollection"
            >
              创建
            </el-button>
          </section>

          <el-table
            :data="collectionPagination.items"
            v-loading="loadingDocumentCollections"
            class="collection-table"
            empty-text="暂无文档集"
          >
            <el-table-column prop="name" label="文档集" min-width="180" show-overflow-tooltip />
            <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
            <el-table-column prop="document_count" label="文档数" width="90" />
            <el-table-column label="创建者" width="130">
              <template #default="{ row }">{{ row.owner_username || `用户 ${row.owner_id}` }}</template>
            </el-table-column>
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" :width="currentUser?.is_admin ? 320 : 140" fixed="right">
              <template #default="{ row }">
                <div class="collection-actions">
                  <el-button @click="showCollectionDocuments(row)">查看文档</el-button>
                  <el-button v-if="currentUser?.is_admin" :icon="Key" @click="openCollectionPermissions(row)">
                    授权
                  </el-button>
                  <el-button v-if="currentUser?.is_admin" type="danger" plain @click="removeDocumentCollection(row)">
                    删除
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="collectionPage"
            v-model:page-size="collectionPageSize"
            :total="documentCollections.length"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            class="collection-pagination"
          />
        </section>

<PermissionGrantDialog
  v-model="collectionPermissionDialogVisible"
  :title="selectedCollection ? `文档集授权：${selectedCollection.name}` : '文档集授权'"
  alert="集合权限会自动覆盖当前和后续移入该文档集的全部文档，并在后端文档列表与 RAG 检索阶段生效。"
  :loading="loadingPermissions"
  :users="collectionPermissionUserOptions"
  :groups="groups"
  :user-grants="selectedCollectionUserPermissions"
  :group-grants="selectedCollectionGroupPermissions"
  :grant-user="grantCollectionUser"
  :grant-group="grantCollectionGroup"
  :revoke-user="revokeCollectionUserPermission"
  :revoke-group="revokeCollectionGroupPermission"
  user-hint="写权限同时包含读取权限。"
  group-hint="部门成员会继承该文档集的权限。"
/>
</template>

<style>
.collection-page {
  display: grid;
  gap: 22px;
  min-width: 0;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: 22px 24px 18px;
}

.collection-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.collection-head h2 {
  margin: 0;
  color: var(--c-111827);
  font-size: 18px;
  font-weight: 740;
}

.collection-head p {
  max-width: 720px;
  margin: 8px 0 0;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.7;
}

.collection-create {
  display: grid;
  grid-template-columns: minmax(220px, 0.8fr) minmax(280px, 1.3fr) auto;
  align-items: center;
  gap: 12px;
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 16px;
}

.collection-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.collection-table {
  width: 100%;
}

.collection-pagination {
  justify-content: flex-end;
  overflow-x: auto;
}

@media (max-width: 900px) {
  .collection-create {
    grid-template-columns: 1fr;
  }
}
</style>
