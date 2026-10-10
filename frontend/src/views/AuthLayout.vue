<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
}>()
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
      <p>{{ subtitle }}</p>
      <slot />
    </section>
  </main>
</template>
