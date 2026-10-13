<script setup lang="ts">
import { onMounted } from 'vue'
import { backendOnline, refreshBackendStatus } from '../stores/system'

defineProps<{
  title: string
  subtitle: string
}>()

onMounted(() => { void refreshBackendStatus() })
</script>

<template>
  <main class="auth-screen">
    <section class="auth-card">
      <div class="brand auth-brand">
        <div class="brand-mark">R</div>
        <div>
          <div class="brand-title">RAG Agent</div>
          <div class="brand-subtitle">企业知识库</div>
        </div>
      </div>
      <h1>{{ title }}</h1>
      <p>面向企业文档的检索问答。上传资料后，按当前账号权限回答，并给出依据。</p>
      <p>{{ subtitle }}</p>
      <el-tag :type="backendOnline ? 'success' : 'info'" effect="plain">{{ backendOnline ? '后端在线' : '后端离线' }}</el-tag>
      <slot />
    </section>
  </main>
</template>

<style>
.auth-form {
display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  align-items: end;
  gap: 12px;
}

.auth-form .el-form-item {
margin-bottom: 0;
}

.auth-form .el-button {
min-height: 32px;
  width: 100%;
}

@media (max-width: 760px) {
.auth-form {
grid-template-columns: 1fr;
}
}

.auth-screen {
display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px 16px;
}

.auth-card {
width: min(440px, 100%);
  border: 1px solid var(--c-dce3ea);
  border-radius: 8px;
  background: var(--c-ffffff);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  padding: 28px 24px 24px;
}

.auth-card .auth-brand {
padding: 0 0 20px;
  margin-bottom: 20px;
}

.auth-card h1 {
margin: 0;
  color: var(--c-111827);
  font-size: 22px;
  font-weight: 760;
  letter-spacing: 0;
}

.auth-card > p {
margin: 8px 0 20px;
  color: var(--c-64748b);
  font-size: 13px;
  line-height: 1.6;
}

.auth-card .auth-form {
grid-template-columns: 1fr;
}

.auth-switch {
margin: 16px 0 0;
  color: var(--c-64748b);
  font-size: 13px;
}

.auth-switch a {
color: var(--c-0f766e);
  font-weight: 650;
  text-decoration: none;
}

.auth-switch a:hover {
text-decoration: underline;
}
</style>
