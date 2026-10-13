<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppSidebar from '../components/layout/AppSidebar.vue'
import AppTopbar from '../components/layout/AppTopbar.vue'
import { AUTH_ERROR_EVENT } from '../api/client'
import { clearSession, currentUser, ensureCurrentUser, token } from '../auth/session'
import { applyAccountRetrievalPreferences, loadChatHistory } from '../stores/chat'
import { refreshDocumentCollections, refreshDocuments } from '../stores/documents'
import { loadPermissionAdminData } from '../stores/permissionActions'
import { refreshBackendStatus } from '../stores/system'

const route = useRoute()
const router = useRouter()

function logout(showMessage = true) {
  clearSession()
  if (showMessage) ElMessage.success('已退出登录')
  if (route.name !== 'login') void router.push({ name: 'login' })
}

function handleAuthExpired() {
  if (!token.value && !currentUser.value) return
  logout(false)
  ElMessage.warning('登录状态已失效，请重新登录')
}

async function loadCurrentUser() {
  if (!token.value) return false
  const user = await ensureCurrentUser()
  if (!user) {
    logout(false)
    return false
  }
  applyAccountRetrievalPreferences(user.id)
  return true
}

function refreshForRoute() {
  const name = String(route.name || '')
  if (name === 'documents' || name === 'collections' || name === 'chat') void refreshDocuments()
  if (name === 'upload' || name === 'documents' || name === 'collections') void refreshDocumentCollections()
  if (name === 'permissions' || name === 'permission-groups' || name === 'permission-audit') void loadPermissionAdminData()
}

onMounted(async () => {
  window.addEventListener(AUTH_ERROR_EVENT, handleAuthExpired)
  await refreshBackendStatus()
  if (!token.value) return
  const ready = await loadCurrentUser()
  if (!ready) return
  await refreshDocuments()
  await refreshDocumentCollections()
  await loadChatHistory()
  refreshForRoute()
})

onBeforeUnmount(() => {
  window.removeEventListener(AUTH_ERROR_EVENT, handleAuthExpired)
})

watch(() => route.fullPath, () => {
  refreshForRoute()
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar />
    <main class="main-panel">
      <AppTopbar />
      <router-view />
    </main>
  </div>
</template>
