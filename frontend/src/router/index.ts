import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { translate } from '@/i18n'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/portal',
    name: 'BuyerPortal',
    component: () => import('@/views/BuyerPortal.vue'),
    meta: { title: 'Buyer portal' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/agent',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'agent',
        name: 'AgentCenter',
        component: () => import('@/views/AgentCenter.vue'),
        meta: { title: 'Agent Center' },
      },
      {
        path: 'ai-chat',
        name: 'AIChat',
        component: () => import('@/views/AIChat.vue'),
        meta: { title: 'AI Chat' },
      },
      {
        path: 'video-studio',
        name: 'VideoStudio',
        component: () => import('@/views/VideoStudio.vue'),
        meta: { title: 'Video Studio' },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: 'Dashboard' },
      },
      {
        path: 'workflows',
        name: 'Workflows',
        component: () => import('@/views/Workflows.vue'),
        meta: { title: 'Workflows' },
      },
      {
        path: 'skills',
        name: 'Skills',
        component: () => import('@/views/Skills.vue'),
        meta: { title: 'Skills' },
      },
      {
        path: 'workflows/:id',
        name: 'WorkflowEditor',
        component: () => import('@/views/WorkflowEditor.vue'),
        meta: { title: 'Workflow Editor' },
      },
      {
        path: 'prospecting',
        name: 'Prospecting',
        component: () => import('@/views/Prospecting.vue'),
        meta: { title: 'Prospecting' },
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { title: 'Customers' },
      },
      {
        path: 'customers/:id',
        name: 'CustomerDetail',
        component: () => import('@/views/CustomerDetail.vue'),
        meta: { title: 'Customer Detail' },
      },
      {
        path: 'fulfillment',
        name: 'Fulfillment',
        component: () => import('@/views/Fulfillment.vue'),
        meta: { title: 'Fulfillment' },
      },
      {
        path: 'orders/:id',
        name: 'OrderDetail',
        component: () => import('@/views/OrderDetail.vue'),
        meta: { title: 'Order Detail' },
      },
      {
        path: 'buyer-assistant',
        name: 'BuyerAssistant',
        component: () => import('@/views/BuyerAssistant.vue'),
        meta: { title: 'Buyer assistant' },
      },
      {
        path: 'operations-assistant',
        name: 'OperationsAssistant',
        component: () => import('@/views/OperationsAssistant.vue'),
        meta: { title: 'Operations assistant' },
      },
      {
        path: 'commerce',
        name: 'CommerceAdmin',
        component: () => import('@/views/CommerceAdmin.vue'),
        meta: { title: 'Catalog and assistant quality' },
      },
      {
        path: 'conversations',
        name: 'Conversations',
        component: () => import('@/views/Conversations.vue'),
        meta: { title: 'Conversations' },
      },
      {
        path: 'conversations/:id',
        name: 'ConversationDetail',
        component: () => import('@/views/ConversationDetail.vue'),
        meta: { title: 'Conversation Detail' },
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/Analytics.vue'),
        meta: { title: 'Analytics' },
      },
      {
        path: 'operations',
        name: 'Operations',
        component: () => import('@/views/Operations.vue'),
        meta: { title: 'Operations', requiresAdmin: true },
      },
      {
        path: 'connectors',
        name: 'Connectors',
        component: () => import('@/views/Connectors.vue'),
        meta: { title: 'Connectors', requiresAdmin: true },
      },
      {
        path: 'operations/dead-letters',
        name: 'DeadLetters',
        component: () => import('@/views/DeadLetters.vue'),
        meta: { title: 'Dead-letter Operations', requiresAdmin: true },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: 'Settings' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard
router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  if (to.meta.title) {
    document.title = `${translate(String(to.meta.title))} - B-agent`
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (authStore.isAuthenticated && !authStore.user) {
    try {
      await authStore.fetchUser()
    } catch {
      await authStore.logout()
      return { name: 'Login', query: { redirect: to.fullPath } }
    }
  }

  if (to.meta.guest && authStore.isAuthenticated) return { name: 'AgentCenter' }
  if (to.meta.requiresAdmin && !authStore.isAdmin) return { name: 'AgentCenter' }
  return true
})

export default router
