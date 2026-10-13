import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { safeRedirect } from '../auth/redirect'
import { consumeAuthFailure, ensureCurrentUser, token } from '../auth/session'
import { resolveGuard } from './guard'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import WorkbenchLayout from '../layouts/WorkbenchLayout.vue'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    guest?: boolean
    title?: string
    subtitle?: string
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { guest: true } },
    { path: '/register', name: 'register', component: RegisterView, meta: { guest: true } },
    {
      path: '/',
      component: WorkbenchLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/documents/upload' },
        { path: 'documents/upload', name: 'upload', component: () => import('../views/upload/UploadView.vue'), meta: { title: '上传文档', subtitle: '上传 PDF、Office、Markdown 或 TXT，后端自动选择原生解析、LiteParse、OCR，完成分块并写入 ChromaDB。' } },
        { path: 'documents', name: 'documents', component: () => import('../views/documents/DocumentListView.vue'), meta: { title: '文档列表', subtitle: '管理可访问文档与文档集，查看入库进度、分块和质量报告。' } },
        { path: 'documents/collections', name: 'collections', component: () => import('../views/documents/CollectionsView.vue'), meta: { title: '文档集', subtitle: '管理可访问文档与文档集，查看入库进度、分块和质量报告。' } },
        { path: 'chat', name: 'chat', component: () => import('../views/chat/ChatView.vue'), meta: { title: '知识问答', subtitle: '先看结论，再查看依据与原文来源；可选择文档集或指定文档提问。' } },
        { path: 'permissions', name: 'permissions', component: () => import('../views/permissions/ResourcesView.vue'), meta: { requiresAdmin: true, title: '资源授权', subtitle: '管理文档与文档集授权、部门成员，并查看权限变更日志。' } },
        { path: 'permissions/groups', name: 'permission-groups', component: () => import('../views/permissions/GroupsView.vue'), meta: { requiresAdmin: true, title: '部门与成员', subtitle: '管理文档与文档集授权、部门成员，并查看权限变更日志。' } },
        { path: 'permissions/audit', name: 'permission-audit', component: () => import('../views/permissions/AuditLogView.vue'), meta: { requiresAdmin: true, title: '变更日志', subtitle: '管理文档与文档集授权、部门成员，并查看权限变更日志。' } },
        { path: 'settings', name: 'settings', component: () => import('../views/settings/SystemOverviewView.vue'), meta: { title: '系统概览', subtitle: '查看模型、解析与运行配置；文档和授权分别在文档管理、权限管理中处理。' } }
      ]
    },
    { path: '/:pathMatch(.*)*', redirect: '/documents/upload' }
  ]
})

router.beforeEach(async (to) => {
  if (to.meta.guest) {
    if (!token.value) return true
    const user = await ensureCurrentUser()
    if (user) return safeRedirect(to.query.redirect)
    consumeAuthFailure()
    return true
  }

  const meta = {
    requiresAuth: to.matched.some((record) => record.meta.requiresAuth),
    requiresAdmin: to.matched.some((record) => record.meta.requiresAdmin)
  }
  const user = meta.requiresAuth || meta.requiresAdmin ? await ensureCurrentUser() : null
  const decision = resolveGuard(
    meta,
    user,
    { path: to.path, fullPath: to.fullPath },
    user ? null : consumeAuthFailure()
  )
  if (decision.kind === 'allow') return true
  if (decision.kind === 'stay') return false
  if (decision.warning) ElMessage.warning(decision.warning)
  if (decision.kind === 'login') return { name: 'login', query: { redirect: decision.redirect } }
  return { name: 'upload' }
})

router.afterEach((to) => {
  const pageTitle = typeof to.meta.title === 'string'
    ? to.meta.title
    : to.name === 'login' ? '登录' : to.name === 'register' ? '注册' : '知识库'
  document.title = `${pageTitle} · RAG Agent 知识库`
})

export default router
