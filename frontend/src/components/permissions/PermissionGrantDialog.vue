<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatTime } from '../../utils/format'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{
  title: string
  alert: string
  loading: boolean
  detailed?: boolean
  users: Array<{ id: number; username: string; is_admin: boolean }>
  groups: Array<{ id: number; name: string }>
  userGrants: Array<{ id: number; user_id: number; user_username?: string | null; can_read: boolean; can_write: boolean; created_at?: string }>
  groupGrants: Array<{ id: number; group_id: number; group_name?: string | null; can_read: boolean; can_write: boolean; created_at?: string }>
  grantUser: (userId: number, canRead: boolean, canWrite: boolean) => Promise<void>
  grantGroup: (groupId: number, canRead: boolean, canWrite: boolean) => Promise<void>
  revokeUser: (row: { id: number }) => Promise<void> | void
  revokeGroup: (row: { id: number }) => Promise<void> | void
  userHint?: string
  groupHint?: string
}>()

const userId = ref<number | null>(null)
const groupId = ref<number | null>(null)
const userRead = ref(true)
const userWrite = ref(false)
const groupRead = ref(true)
const groupWrite = ref(false)

watch(visible, (open) => {
  if (!open) return
  userId.value = null
  groupId.value = null
  userRead.value = true
  userWrite.value = false
  groupRead.value = true
  groupWrite.value = false
})

async function saveUser() {
  if (userId.value === null) return
  await props.grantUser(userId.value, userRead.value, userWrite.value)
  userId.value = null
  userRead.value = true
  userWrite.value = false
}

async function saveGroup() {
  if (groupId.value === null) return
  await props.grantGroup(groupId.value, groupRead.value, groupWrite.value)
  groupId.value = null
  groupRead.value = true
  groupWrite.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="title" :width="detailed ? 'min(720px, 94vw)' : 'min(760px, 94vw)'">
    <div v-loading="loading" class="permission-dialog-body">
      <el-alert type="info" show-icon :closable="false" :title="alert" />
      <p class="permission-overlap-note">用户授权与部门授权同时生效。写权限同时包含读取权限。</p>
      <div class="permission-section-title">
        <strong>用户授权</strong>
        <span>{{ userHint || '写权限同时包含读取权限。' }}</span>
      </div>
      <section class="permission-form">
        <el-select v-model="userId" filterable placeholder="选择用户">
          <el-option v-for="user in users" :key="user.id" :label="`${user.username}${user.is_admin ? '（管理员）' : ''}`" :value="user.id" />
        </el-select>
        <el-checkbox v-model="userRead">可读</el-checkbox>
        <el-checkbox v-model="userWrite">可写</el-checkbox>
        <el-button type="primary" @click="saveUser">保存授权</el-button>
      </section>
      <el-table :data="userGrants" size="small" empty-text="暂无用户授权">
        <el-table-column label="用户" min-width="180">
          <template #default="{ row }">{{ row.user_username || `用户 ${row.user_id}` }}</template>
        </el-table-column>
        <el-table-column label="可读" :width="detailed ? 90 : 80">
          <template #default="{ row }">
            <el-tag v-if="detailed" :type="row.can_read ? 'success' : 'info'" effect="plain">{{ row.can_read ? '是' : '否' }}</el-tag>
            <template v-else>{{ row.can_read ? '是' : '否' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="可写" :width="detailed ? 90 : 80">
          <template #default="{ row }">
            <el-tag v-if="detailed" :type="row.can_write ? 'success' : 'info'" effect="plain">{{ row.can_write ? '是' : '否' }}</el-tag>
            <template v-else>{{ row.can_write ? '是' : '否' }}</template>
          </template>
        </el-table-column>
        <el-table-column v-if="detailed" label="授权时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || null) }}</template>
        </el-table-column>
        <el-table-column label="操作" :width="detailed ? 100 : 90">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="revokeUser(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="permission-section-title">
        <strong>部门授权</strong>
        <span>{{ groupHint || '部门成员会继承这里的权限。' }}</span>
      </div>
      <section class="permission-form">
        <el-select v-model="groupId" filterable placeholder="选择用户组 / 部门">
          <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
        </el-select>
        <el-checkbox v-model="groupRead">可读</el-checkbox>
        <el-checkbox v-model="groupWrite">可写</el-checkbox>
        <el-button type="primary" @click="saveGroup">{{ detailed ? '保存部门授权' : '保存授权' }}</el-button>
      </section>
      <el-table :data="groupGrants" size="small" empty-text="暂无部门授权">
        <el-table-column label="部门" min-width="180">
          <template #default="{ row }">{{ row.group_name || `部门 ${row.group_id}` }}</template>
        </el-table-column>
        <el-table-column label="可读" :width="detailed ? 90 : 80">
          <template #default="{ row }">
            <el-tag v-if="detailed" :type="row.can_read ? 'success' : 'info'" effect="plain">{{ row.can_read ? '是' : '否' }}</el-tag>
            <template v-else>{{ row.can_read ? '是' : '否' }}</template>
          </template>
        </el-table-column>
        <el-table-column label="可写" :width="detailed ? 90 : 80">
          <template #default="{ row }">
            <el-tag v-if="detailed" :type="row.can_write ? 'success' : 'info'" effect="plain">{{ row.can_write ? '是' : '否' }}</el-tag>
            <template v-else>{{ row.can_write ? '是' : '否' }}</template>
          </template>
        </el-table-column>
        <el-table-column v-if="detailed" label="授权时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at || null) }}</template>
        </el-table-column>
        <el-table-column label="操作" :width="detailed ? 100 : 90">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="revokeGroup(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>

<style>
.audit-table {
width: 100%;
}

.permission-dialog-body {
display: grid;
  gap: 16px;
}

.permission-form {
display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto minmax(108px, auto);
  align-items: center;
  gap: 12px;
}

.permission-section-title {
display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--c-e2e8f0);
  padding-top: 4px;
}

.permission-section-title strong {
color: var(--c-111827);
  font-size: 13px;
  font-weight: 740;
}

.permission-section-title span {
color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.45;
}

@media (max-width: 760px) {
.permission-form {
grid-template-columns: 1fr;
}
}
</style>
