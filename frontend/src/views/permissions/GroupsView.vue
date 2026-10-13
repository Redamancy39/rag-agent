<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { currentUser } from '../../auth/session'
import { groupForm, groupMemberForm, groupMemberOptions, groups, loadingGroups, selectedGroup, selectedGroupMembers } from '../../stores/permissionAdmin'
import { loadPermissionAdminData, removeGroup, removeSelectedGroupMember, selectGroup, submitGroup, submitGroupMember } from '../../stores/permissionActions'
import { formatTime } from '../../utils/format'
</script>

<template>
            <section v-if="currentUser?.is_admin" class="group-page">
              <div class="group-head">
                <p>管理员可以创建部门，将用户加入部门，并在文档权限弹窗中按部门批量授权。</p>
                <el-button :icon="Refresh" :loading="loadingGroups" @click="loadPermissionAdminData">
                  刷新
                </el-button>
              </div>

              <section class="group-admin-form">
                <el-input aria-label="部门名称" v-model="groupForm.name" placeholder="部门名称，例如：法规部" />
                <el-input aria-label="部门说明" v-model="groupForm.description" placeholder="部门说明，可选" />
                <el-button type="primary" :loading="loadingGroups" @click="submitGroup">
                  创建
                </el-button>
              </section>

              <section class="group-admin-grid">
                <el-table
                  :data="groups"
                  v-loading="loadingGroups"
                  class="admin-table"
                  empty-text="暂无用户组 / 部门"
                >
                  <el-table-column prop="name" label="部门" min-width="160" show-overflow-tooltip />
                  <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
                  <el-table-column label="创建时间" width="170">
                    <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="180" fixed="right">
                    <template #default="{ row }">
                      <div class="group-actions">
                        <el-button @click="selectGroup(row)">成员</el-button>
                        <el-button type="danger" plain @click="removeGroup(row)">
                          删除
                        </el-button>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>

                <section class="group-member-panel">
                  <header>
                    <div>
                      <h3>{{ selectedGroup ? selectedGroup.name : '请选择部门' }}</h3>
                      <p>成员会继承该部门被授予的文档读取权限。</p>
                    </div>
                  </header>

                  <section class="group-member-form">
                    <el-select
                      v-model="groupMemberForm.user_id"
                      filterable
                      placeholder="选择用户"
                      :disabled="!selectedGroup"
                    >
                      <el-option
                        v-for="user in groupMemberOptions"
                        :key="user.id"
                        :label="`${user.username}${user.is_admin ? '（管理员）' : ''}`"
                        :value="user.id"
                      />
                    </el-select>
                    <el-button
                      type="primary"
                      plain
                      :disabled="!selectedGroup"
                      :loading="loadingGroups"
                      @click="submitGroupMember"
                    >
                      加入
                    </el-button>
                  </section>

                  <el-table
                    :data="selectedGroupMembers"
                    empty-text="暂无成员"
                  >
                    <el-table-column label="用户名" min-width="140">
                      <template #default="{ row }">{{ row.user_username || `用户 ${row.user_id}` }}</template>
                    </el-table-column>
                    <el-table-column label="加入时间" width="150">
                      <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="100">
                      <template #default="{ row }">
                        <el-button type="danger" plain @click="removeSelectedGroupMember(row)">
                          移除
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </section>
              </section>
            </section>
</template>

<style>
.group-page {
  display: grid;
  gap: 22px;
  min-width: 0;
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: 22px 24px 18px;
}

.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.group-head p {
  margin: 0;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.7;
}

.group-admin-form {
  display: grid;
  grid-template-columns: minmax(200px, 0.8fr) minmax(260px, 1.2fr) auto;
  align-items: center;
  gap: 12px;
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 16px;
}

.group-admin-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  align-items: start;
  gap: 20px;
  min-width: 0;
}

.group-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.admin-table {
width: 100%;
}

.group-member-panel {
  display: grid;
  align-content: start;
  gap: 16px;
  min-width: 0;
  border: 1px solid var(--c-e2e8f0);
  border-radius: 8px;
  background: var(--c-f8fafc);
  padding: 16px;
}

.group-member-panel header {
display: flex;
  justify-content: space-between;
  gap: 12px;
}

.group-member-panel h3 {
margin: 0;
  color: var(--c-111827);
  font-size: 14px;
  font-weight: 740;
}

.group-member-panel p {
margin: 5px 0 0;
  color: var(--c-64748b);
  font-size: 12px;
  line-height: 1.45;
}

.group-member-form {
display: grid;
  grid-template-columns: minmax(0, 1fr) 76px;
  gap: 10px;
}

@media (max-width: 1320px) {
.group-admin-grid {
grid-template-columns: 1fr;
}
}

@media (max-width: 760px) {
.group-admin-form,
.group-member-form {
grid-template-columns: 1fr;
}
}
</style>
