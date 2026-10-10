import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { safeRedirect } from '../auth/redirect'
import { consumeAuthFailure, ensureCurrentUser, token } from '../auth/session'
import RouteMarker from '../components/RouteMarker.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import App from '../App.vue'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
    guest?: boolean
    view?: 'upload' | 'documents' | 'permissions' | 'chat' | 'settings'
    section?: 'upload' | 'files' | 'collections' | 'resources' | 'groups' | 'audit'
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { guest: true } },
    { path: '/register', name: 'register', component: RegisterView, meta: { guest: true } },
    {
      path: '/',
      component: App,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/documents/upload' },
        { path: 'documents/upload', name: 'upload', component: RouteMarker, meta: { view: 'upload', section: 'upload' } },
        { path: 'documents', name: 'documents', component: RouteMarker, meta: { view: 'documents', section: 'files' } },
        {
          path: 'documents/collections',
          name: 'collections',
          component: RouteMarker,
          meta: { view: 'documents', section: 'collections' }
        },
        { path: 'chat', name: 'chat', component: RouteMarker, meta: { view: 'chat' } },
        {
          path: 'permissions',
          name: 'permissions',
          component: RouteMarker,
          meta: { view: 'permissions', section: 'resources', requiresAdmin: true }
        },
        {
          path: 'permissions/groups',
          name: 'permission-groups',
          component: RouteMarker,
          meta: { view: 'permissions', section: 'groups', requiresAdmin: true }
        },
        {
          path: 'permissions/audit',
          name: 'permission-audit',
          component: RouteMarker,
          meta: { view: 'permissions', section: 'audit', requiresAdmin: true }
        },
        { path: 'settings', name: 'settings', component: RouteMarker, meta: { view: 'settings' } }
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

  const authRequired = to.matched.some((record) => record.meta.requiresAuth)
  const adminRequired = to.matched.some((record) => record.meta.requiresAdmin)
  if (!authRequired && !adminRequired) return true

  const user = await ensureCurrentUser()
  if (!user) {
    if (consumeAuthFailure() === 'unauthorized') {
      ElMessage.warning('登录状态已失效，请重新登录')
    }
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (adminRequired && !user.is_admin) {
    ElMessage.warning('权限管理仅供管理员使用')
    return to.path === '/documents/upload' ? false : { name: 'upload' }
  }
  return true
})

export default router
