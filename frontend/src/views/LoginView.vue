<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { loginUser } from '../api/client'
import { safeRedirect } from '../auth/redirect'
import { ensureCurrentUser, setToken } from '../auth/session'
import AuthLayout from './AuthLayout.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: '',
  password: ''
})

async function submit() {
  if (loading.value) return
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    const result = await loginUser({
      username: form.username,
      password: form.password
    })
    setToken(result.access_token)
    const user = await ensureCurrentUser()
    if (!user) {
      ElMessage.error('登录状态无效，请重试')
      return
    }
    ElMessage.success('登录成功')
    await router.replace(safeRedirect(route.query.redirect))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthLayout title="登录" subtitle="登录后进入工作台。文档、问答和权限界面需要有效的 JWT。">
    <el-form class="auth-form" :model="form" label-position="top">
      <el-form-item label="用户名">
        <el-input v-model="form.username" :prefix-icon="User" autocomplete="username" placeholder="demo_user" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input
          v-model="form.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          autocomplete="current-password"
          placeholder="至少 8 位"
          @keyup.enter="submit"
        />
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="submit">登录并进入工作台</el-button>
    </el-form>
    <p class="auth-switch">
      没有账号？
      <RouterLink :to="{ name: 'register', query: route.query }">注册</RouterLink>
    </p>
  </AuthLayout>
</template>
