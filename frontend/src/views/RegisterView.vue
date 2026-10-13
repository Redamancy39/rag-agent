<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { loginUser, registerUser } from '../api/client'
import { safeRedirect } from '../auth/redirect'
import { ensureCurrentUser, setToken } from '../auth/session'
import AuthLayout from './AuthLayout.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const form = reactive({
  username: '',
  email: '',
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
    await registerUser({
      username: form.username,
      email: form.email || undefined,
      password: form.password
    })
    const result = await loginUser({
      username: form.username,
      password: form.password
    })
    setToken(result.access_token)
    const user = await ensureCurrentUser()
    if (!user) {
      ElMessage.error('注册成功，但登录状态无效，请重新登录')
      await router.replace({ name: 'login', query: route.query })
      return
    }
    ElMessage.success('注册成功，已自动登录')
    await router.replace(safeRedirect(route.query.redirect))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthLayout title="注册" subtitle="注册普通账号后会自动登录。管理员账号由后端配置。">
    <el-form class="auth-form" :model="form" label-position="top">
      <el-form-item label="用户名">
        <el-input v-model="form.username" :prefix-icon="User" autocomplete="username" placeholder="demo_user" />
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input v-model="form.email" type="email" autocomplete="email" placeholder="demo@example.com" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input
          v-model="form.password"
          :prefix-icon="Lock"
          type="password"
          show-password
          autocomplete="new-password"
          placeholder="至少 8 位"
          @keyup.enter="submit"
        />
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="submit">注册并登录</el-button>
    </el-form>
    <p class="auth-switch">
      已有账号？
      <RouterLink :to="{ name: 'login', query: route.query }">去登录</RouterLink>
    </p>
  </AuthLayout>
</template>
