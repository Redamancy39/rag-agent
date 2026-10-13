<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Document, Files, Key, Setting } from '@element-plus/icons-vue'
import { currentUser } from '../../auth/session'
import { backendOnline } from '../../stores/system'

const route = useRoute()
const router = useRouter()
const expanded = ref<string | null>(route.path.startsWith('/permissions') ? 'permissions' : 'documents')
const documentItems = [
  { label: '上传文档', name: 'upload' },
  { label: '文档列表', name: 'documents' },
  { label: '文档集', name: 'collections' }
]
const permissionItems = [
  { label: '资源授权', name: 'permissions' },
  { label: '部门与成员', name: 'permission-groups' },
  { label: '变更日志', name: 'permission-audit' }
]
watch(() => route.name, (name) => {
  if (name === 'upload' || name === 'documents' || name === 'collections') expanded.value = 'documents'
  if (name === 'permissions' || name === 'permission-groups' || name === 'permission-audit') expanded.value = 'permissions'
})
function toggle(group: string) { expanded.value = expanded.value === group ? null : group }
function open(name: string) { void router.push({ name }) }
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">R</div>
      <div>
        <div class="brand-title">RAG Agent</div>
        <div class="brand-subtitle">企业知识库</div>
      </div>
    </div>
    <nav class="nav-list" aria-label="主导航">
      <div class="nav-group">
        <button class="nav-item nav-group-toggle" :class="{ 'group-active': ['upload','documents','collections'].includes(String(route.name)) }" type="button" :aria-expanded="expanded === 'documents'" aria-controls="document-submenu" @click="toggle('documents')">
          <el-icon><Files /></el-icon><span>文档管理</span>
          <el-icon class="nav-chevron" :class="{ expanded: expanded === 'documents' }"><ArrowRight /></el-icon>
        </button>
        <Transition name="nav-submenu" appear :duration="{ enter: 380, leave: 0 }">
          <div v-if="expanded === 'documents'" id="document-submenu" class="nav-submenu" role="region" aria-label="文档管理子菜单">
            <div class="nav-submenu-inner">
              <button v-for="(item, index) in documentItems" :key="item.name" class="nav-subitem" :class="{ active: route.name === item.name }" :style="{ '--item-index': index }" :aria-current="route.name === item.name ? 'page' : undefined" type="button" @click="open(item.name)">{{ item.label }}</button>
            </div>
          </div>
        </Transition>
      </div>
      <button class="nav-item" :class="{ active: route.name === 'chat' }" type="button" @click="open('chat')"><el-icon><Document /></el-icon><span>知识问答</span></button>
      <div v-if="currentUser?.is_admin" class="nav-group">
        <button class="nav-item nav-group-toggle" :class="{ 'group-active': String(route.name).startsWith('permission') }" type="button" :aria-expanded="expanded === 'permissions'" aria-controls="permission-submenu" @click="toggle('permissions')">
          <el-icon><Key /></el-icon><span>权限管理</span>
          <el-icon class="nav-chevron" :class="{ expanded: expanded === 'permissions' }"><ArrowRight /></el-icon>
        </button>
        <Transition name="nav-submenu" :duration="{ enter: 380, leave: 0 }">
          <div v-if="expanded === 'permissions'" id="permission-submenu" class="nav-submenu" role="region" aria-label="权限管理子菜单">
            <div class="nav-submenu-inner">
              <button v-for="(item, index) in permissionItems" :key="item.name" class="nav-subitem" :class="{ active: route.name === item.name }" :style="{ '--item-index': index }" :aria-current="route.name === item.name ? 'page' : undefined" type="button" @click="open(item.name)">{{ item.label }}</button>
            </div>
          </div>
        </Transition>
      </div>
      <button class="nav-item" :class="{ active: route.name === 'settings' }" type="button" @click="open('settings')"><el-icon><Setting /></el-icon><span>系统概览</span></button>
    </nav>
    <div class="sidebar-footer">
      <div class="health-dot" :class="{ online: backendOnline }" />
      <span>{{ backendOnline ? '后端在线' : '后端离线' }}</span>
    </div>
  </aside>
</template>
