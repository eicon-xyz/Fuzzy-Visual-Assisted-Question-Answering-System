import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { noAuth: true },
  },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '总览' },
      },
      {
        path: 'failures',
        name: 'Failures',
        component: () => import('../views/Failures.vue'),
        meta: { title: '失败归因' },
      },
      {
        path: 'flow',
        name: 'FlowMonitor',
        component: () => import('../views/FlowMonitor.vue'),
        meta: { title: '数据流监控' },
      },
      {
        path: 'config',
        name: 'SystemConfig',
        component: () => import('../views/SystemConfig.vue'),
        meta: { title: '系统配置' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('../views/Users.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'health',
        name: 'HealthMonitor',
        component: () => import('../views/HealthMonitor.vue'),
        meta: { title: '健康监控' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('../views/Users.vue'),
        meta: { title: '用户管理', requireAdmin: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('hajimi_access_token')
  if (!to.meta.noAuth && !token) {
    return '/login'
  }
  // 已登录访问登录页 → 重定向到 dashboard
  if (to.path === '/login' && token) {
    return '/dashboard'
  }
})

export default router
