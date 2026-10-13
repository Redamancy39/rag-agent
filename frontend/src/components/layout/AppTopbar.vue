<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Files, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { clearSession, currentUser, isLoggedIn } from '../../auth/session'
import { folderPending, folderRunning, folderStopping } from '../../stores/folderUpload'
import { refreshBackendStatus } from '../../stores/system'

const route = useRoute()
const router = useRouter()
const title = computed(() => String(route.meta.title || '知识库'))
const subtitle = computed(() => String(route.meta.subtitle || ''))

function logout() {
  clearSession()
  ElMessage.success('已退出登录')
  if (route.name !== 'login') void router.push({ name: 'login' })
}
</script>

<template>
  <header class="topbar">
    <div>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
    </div>
    <div class="topbar-actions">
      <el-button v-if="folderRunning" :icon="Files" plain @click="router.push({ name: 'upload' })">
        {{ folderStopping ? '正在停止后续上传' : `文件夹处理中 · 待提交 ${folderPending}` }}
      </el-button>
      <el-button :icon="Refresh" @click="refreshBackendStatus">刷新状态</el-button>
      <el-button v-if="isLoggedIn" plain @click="logout">{{ currentUser?.username }}，退出</el-button>
    </div>
  </header>
</template>
