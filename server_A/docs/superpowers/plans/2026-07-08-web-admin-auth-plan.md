# HAJIMI Web-Admin 认证对接 & 用户管理 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web-admin 对接后端 JWT 认证 API，新增用户管理页面，去掉 Mock 数据。

**Architecture:** API 层从 Mock 模式切换到真实 API 调用，响应拦截器加 401→refresh→重试逻辑。登录页对接 `/api/auth/login`。新增 `Users.vue` 页面（列表/统计/重置密码/删除）。侧边栏加菜单项。

**Tech Stack:** Vue 3 + Composition API + Element Plus + Axios

## Global Constraints

- 所有 API 请求走 Vite proxy（`/api` → `http://127.0.0.1:8010`）
- Token 存 localStorage: `hajimi_access_token`, `hajimi_refresh_token`, `hajimi_user` (JSON)
- 响应拦截器：收到 401 → 用 refresh_token 调 `/api/auth/refresh` → 成功则更新 token 并重试原请求 → 失败跳转登录页
- 登出调 `/api/auth/logout` 后清空 localStorage
- 用户管理页仅 admin 可见
- 去掉 `USE_MOCK` 开关、`delay()`、所有 `MOCK` 对象 —— 真实 API 已在后端就绪
- 所有新端点统一使用 `{success: true/false, data/error: {...}}` 响应格式

---

### Task 1: 重写 API 层 — 去掉 Mock，加 Token 刷新拦截器

**Files:**
- Modify: `D:\HAJI\web-admin\src\api\index.js` (完全重写)
- Modify: `D:\HAJI\web-admin\src\api\admin.js` (删掉 Mock 数据，函数直接透传 API 调用)
- Modify: `D:\HAJI\web-admin\src\main.js` (去掉 `autoDetectServer`)

**Interfaces:**
- Produces: `api` (axios instance, 带 refresh 拦截器), `admin.js` 中所有现有函数签名不变

- [ ] **Step 1: 重写 `src/api/index.js`**

```javascript
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

const DEMO_KEY = 'hajimi-demo-2026'

// ── Token 工具函数 ──

function getAccessToken() {
  return localStorage.getItem('hajimi_access_token')
}

function getRefreshToken() {
  return localStorage.getItem('hajimi_refresh_token')
}

function setTokens(accessToken, refreshToken) {
  localStorage.setItem('hajimi_access_token', accessToken)
  localStorage.setItem('hajimi_refresh_token', refreshToken)
}

function clearAuth() {
  localStorage.removeItem('hajimi_access_token')
  localStorage.removeItem('hajimi_refresh_token')
  localStorage.removeItem('hajimi_user')
}

// ── 请求拦截 ──

api.interceptors.request.use((config) => {
  const url = config.url || ''

  // Admin 路由带 X-Admin-Key（兼容模式）
  if (url.startsWith('/admin') || url.includes('/admin/')) {
    config.headers['X-Admin-Key'] = DEMO_KEY
  } else if (!url.startsWith('/auth')) {
    // 非 auth 路由带 Demo Key（demo 路由）
    config.headers['X-Demo-Key'] = DEMO_KEY
  }

  // 如果有 access_token，优先带 JWT
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

// ── 响应拦截 ──

let isRefreshing = false
let refreshQueue = []

function onRefreshed(newToken) {
  refreshQueue.forEach(({ resolve }) => resolve(newToken))
  refreshQueue = []
}

function onRefreshFailed(err) {
  refreshQueue.forEach(({ reject }) => reject(err))
  refreshQueue = []
}

api.interceptors.response.use(
  (res) => res.data,
  async (err) => {
    const originalRequest = err.config

    // 401 → 尝试刷新
    if (err.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = getRefreshToken()

      if (!refreshToken) {
        clearAuth()
        window.location.hash = '#/login'
        return Promise.reject(err)
      }

      if (isRefreshing) {
        // 已有刷新在进行中，排队等待
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject })
        }).then((newToken) => {
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          originalRequest._retry = true
          return api(originalRequest)
        })
      }

      isRefreshing = true
      originalRequest._retry = true

      try {
        const res = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken,
        })
        const data = res.data
        if (data.success) {
          const newAccess = data.data.access_token
          const newRefresh = data.data.refresh_token
          setTokens(newAccess, newRefresh)
          localStorage.setItem('hajimi_user', JSON.stringify(data.data.user))
          onRefreshed(newAccess)
          originalRequest.headers.Authorization = `Bearer ${newAccess}`
          return api(originalRequest)
        }
      } catch (refreshErr) {
        onRefreshFailed(refreshErr)
        clearAuth()
        ElMessage.error('登录已过期，请重新登录')
        window.location.hash = '#/login'
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }

    // 非 401 → 显示错误
    const msg = err.response?.data?.error?.message
      || err.response?.data?.detail?.error?.message
      || err.message
    ElMessage.error(msg)
    return Promise.reject(err)
  },
)

export { setTokens, clearAuth, getAccessToken, getRefreshToken }
export default api
```

- [ ] **Step 2: 简化 `src/api/admin.js` — 删掉所有 Mock 数据**

```javascript
/**
 * HAJIMI Admin API 服务层
 * 全部 /api/admin/* 端点，真实 API 调用。
 * 新增 /api/auth/* 认证端点。
 */
import api from './index'

// ═══════════════════════════════════════════
//  认证 API
// ═══════════════════════════════════════════

export async function authLogin(username, password) {
  return api.post('/auth/login', { username, password })
}

export async function authRegister(username, password) {
  return api.post('/auth/register', { username, password })
}

export async function authRefresh(refreshToken) {
  return api.post('/auth/refresh', { refresh_token: refreshToken })
}

export async function authLogout(refreshToken) {
  return api.post('/auth/logout', { refresh_token: refreshToken })
}

// ═══════════════════════════════════════════
//  用户管理 API（新增）
// ═══════════════════════════════════════════

export async function fetchUsersList(params = {}) {
  return api.get('/admin/users/list', { params })
}

export async function fetchUserStats(userId) {
  return api.get(`/admin/users/stats/${userId}`)
}

export async function resetUserPassword(userId, newPassword) {
  return api.post('/admin/users/reset-password', { user_id: userId, new_password: newPassword })
}

export async function deleteUser(userId) {
  return api.delete(`/admin/users/${userId}`)
}

// ═══════════════════════════════════════════
//  仪表盘 API（原 Mock 函数，去掉 Mock 直接透传）
// ═══════════════════════════════════════════

export async function fetchOverview(range = '24h') {
  return api.get('/admin/stats/overview', { params: { range } })
}

export async function fetchTrend(metric = 'volume', range = '24h') {
  return api.get('/admin/stats/trend', { params: { metric, range } })
}

export async function fetchFeedback() {
  return api.get('/admin/stats/feedback')
}

export async function fetchTopTasks(limit = 10, range = '7d') {
  return api.get('/admin/stats/top-tasks', { params: { limit, range } })
}

export async function fetchRedline(limit = 5) {
  return api.get('/admin/stats/redline', { params: { limit } })
}

export async function fetchFailuresStats(params = {}) {
  return api.get('/admin/failures/stats', { params })
}

export async function fetchFailuresList(params = {}) {
  return api.get('/admin/failures/list', { params })
}

export async function fetchFailureDetail(taskId) {
  return api.get(`/admin/failures/detail/${taskId}`)
}

export async function fetchFlowTopology() {
  return api.get('/admin/flow/topology')
}

export async function fetchFlowMetrics(apiPath = '/api/demo/process', range = '1h') {
  return api.get('/admin/flow/metrics', { params: { api_path: apiPath, range } })
}

export async function fetchFlowVersions() {
  return api.get('/admin/flow/versions')
}

export async function fetchMonitorHealth() {
  return api.get('/admin/monitor/health')
}

export async function fetchAlerts(params = {}) {
  return api.get('/admin/monitor/alerts', { params })
}

export async function markAlertRead(alertId) {
  return api.post(`/admin/monitor/alerts/${alertId}/read`)
}

export async function markAllAlertsRead() {
  return api.post('/admin/monitor/alerts/read-all')
}

export async function fetchConfigCurrent() {
  return api.get('/admin/config/current')
}

export async function deployConfig(config) {
  return api.post('/admin/config/deploy', { config })
}

export async function fetchDeployLogs(limit = 20) {
  return api.get('/admin/config/deploy-logs', { params: { limit } })
}

// ═══════════════════════════════════════════
//  GPU OmniParser 监控
// ═══════════════════════════════════════════

const GPU_API_URL = 'http://127.0.0.1:9800'

export async function fetchGpuHealth() {
  try {
    const res = await fetch(`${GPU_API_URL}/health`, { signal: AbortSignal.timeout(5000) })
    return await res.json()
  } catch {
    return null
  }
}

export async function fetchGpuProbe() {
  try {
    const res = await fetch(`${GPU_API_URL}/probe/`, { signal: AbortSignal.timeout(5000) })
    return await res.json()
  } catch {
    return null
  }
}
```

- [ ] **Step 3: 修改 `src/main.js` — 去掉 `autoDetectServer`**

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
```

- [ ] **Step 4: 验证 API 层编译通过**

Run:
```bash
cd D:\HAJI\web-admin && npm run build
```
Expected: 无编译错误（可能有未使用变量警告，忽略）。

- [ ] **Step 5: Commit**

```bash
cd D:\HAJI\web-admin
git add src/api/index.js src/api/admin.js src/main.js
git commit -m "feat: remove mock data, add JWT token refresh interceptor"
```

---

### Task 2: 重写 Login.vue — 对接真实登录 API

**Files:**
- Modify: `D:\HAJI\web-admin\src\views\Login.vue`

**Interfaces:**
- Consumes: `authLogin` from `src/api/admin.js` (Task 1), `setTokens` from `src/api/index.js` (Task 1)

- [ ] **Step 1: 重写 `Login.vue` 的 script 部分**

模板和样式不变，只替换 `<script setup>` 块：

```javascript
<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { authLogin } from '../api/admin'
import { setTokens } from '../api/index'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: 'admin',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function login() {
  loading.value = true
  try {
    const res = await authLogin(form.username, form.password)
    if (res.success) {
      // 存储 token + 用户信息
      setTokens(res.data.access_token, res.data.refresh_token)
      localStorage.setItem('hajimi_user', JSON.stringify(res.data.user))
      ElMessage.success('登录成功')
      router.replace('/dashboard')
    } else {
      ElMessage.error(res.error?.message || '登录失败')
    }
  } catch (err) {
    // 错误已由拦截器处理显示，这里只需停止 loading
  } finally {
    loading.value = false
  }
}
</script>
```

- [ ] **Step 2: 更新模板中提示文字**

将 `Demo 阶段 · 默认账号 admin@hajimi.local` 改为 `管理员账号 · 初始密码 admin`：

```html
<div style="text-align: center; color: #c0c4cc; font-size: 12px">
  管理员账号 · 初始密码 admin
</div>
```

- [ ] **Step 3: 编译验证**

```bash
cd D:\HAJI\web-admin && npm run build
```
Expected: 编译成功。

- [ ] **Step 4: Commit**

```bash
cd D:\HAJI\web-admin
git add src/views/Login.vue
git commit -m "feat: connect login page to real auth API"
```

---

### Task 3: 更新路由守卫 + AppLayout 登出

**Files:**
- Modify: `D:\HAJI\web-admin\src\router\index.js`
- Modify: `D:\HAJI\web-admin\src\components\AppLayout.vue`

**Interfaces:**
- Consumes: `clearAuth` from Task 1

- [ ] **Step 1: 更新路由守卫 — 加用户信息恢复**

修改 `src/router/index.js`：

```javascript
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
```

- [ ] **Step 2: 更新 AppLayout — 显示用户名 + 调 logout API**

修改 `src/components/AppLayout.vue` 的 script 部分：

```javascript
<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authLogout } from '../api/admin'
import { clearAuth, getRefreshToken } from '../api/index'

const route = useRoute()
const router = useRouter()

const username = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem('hajimi_user') || '{}')
    return user.username || 'admin'
  } catch {
    return 'admin'
  }
})

async function logout() {
  try {
    const rt = getRefreshToken()
    if (rt) {
      await authLogout(rt)
    }
  } catch {
    // 忽略 logout API 错误
  }
  clearAuth()
  router.replace('/login')
}
</script>
```

模板中 `admin@hajimi.local` 替换为 `{{ username }}`：

```html
<span style="margin-right: 12px; color: #909399">{{ username }}</span>
```

侧边栏加"用户管理"菜单（在"健康监控"之后）：

```html
<el-menu-item index="/users">
  <el-icon><User /></el-icon>
  <span>用户管理</span>
</el-menu-item>
```

- [ ] **Step 3: 编译验证**

```bash
cd D:\HAJI\web-admin && npm run build
```
Expected: 编译成功。

- [ ] **Step 4: Commit**

```bash
cd D:\HAJI\web-admin
git add src/router/index.js src/components/AppLayout.vue
git commit -m "feat: add users route, update logout to call API, show username"
```

---

### Task 4: 新增用户管理页面 `Users.vue`

**Files:**
- Create: `D:\HAJI\web-admin\src\views\Users.vue`

**Interfaces:**
- Consumes: `fetchUsersList`, `fetchUserStats`, `resetUserPassword`, `deleteUser` from Task 1

- [ ] **Step 1: 创建 `src/views/Users.vue`**

```vue
<template>
  <div>
    <!-- 用户列表表格 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>用户列表</span>
          <el-input
            v-model="searchText"
            placeholder="搜索用户名"
            clearable
            style="width: 240px"
            @clear="loadUsers"
            @keyup.enter="loadUsers"
          >
            <template #append>
              <el-button @click="loadUsers">搜索</el-button>
            </template>
          </el-input>
        </div>
      </template>

      <el-table :data="users" stripe v-loading="tableLoading">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '管理员' : '用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="task_count" label="任务数" width="80" />
        <el-table-column prop="last_login_at" label="最后登录" width="170">
          <template #default="{ row }">
            {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '从未登录' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="showStats(row)">统计</el-button>
            <el-button type="warning" link @click="showResetDialog(row)">重置密码</el-button>
            <el-button type="danger" link @click="confirmDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadUsers"
          @current-change="loadUsers"
        />
      </div>
    </el-card>

    <!-- 用户统计抽屉 -->
    <el-drawer v-model="statsVisible" title="用户统计" direction="rtl" size="400px">
      <template v-if="stats">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="用户名">{{ stats.username }}</el-descriptions-item>
          <el-descriptions-item label="总任务数">{{ stats.total_tasks }}</el-descriptions-item>
          <el-descriptions-item label="成功率">{{ (stats.success_rate * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="失败次数">{{ stats.total_failures }}</el-descriptions-item>
          <el-descriptions-item label="反馈数">{{ stats.total_feedback }}</el-descriptions-item>
          <el-descriptions-item label="最后活跃">
            {{ stats.last_active_at ? new Date(stats.last_active_at).toLocaleString() : '无记录' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template v-else>
        <el-skeleton :rows="8" />
      </template>
    </el-drawer>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="400px">
      <el-form :model="resetForm" label-width="80px">
        <el-form-item label="用户名">
          <span>{{ resetForm.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="resetForm.newPassword" type="password" placeholder="至少6位" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetLoading" @click="doResetPassword">
          确定重置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchUsersList, fetchUserStats, resetUserPassword, deleteUser } from '../api/admin'

const users = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchText = ref('')
const tableLoading = ref(false)

// 统计
const statsVisible = ref(false)
const stats = ref(null)

// 重置密码
const resetVisible = ref(false)
const resetLoading = ref(false)
const resetForm = reactive({ userId: '', username: '', newPassword: '' })

async function loadUsers() {
  tableLoading.value = true
  try {
    const res = await fetchUsersList({
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchText.value || undefined,
    })
    if (res.success) {
      users.value = res.data.items
      total.value = res.data.total
    } else {
      ElMessage.error(res.error?.message || '加载用户列表失败')
    }
  } catch {
    // handled by interceptor
  } finally {
    tableLoading.value = false
  }
}

async function showStats(row) {
  statsVisible.value = true
  stats.value = null
  try {
    const res = await fetchUserStats(row.user_id)
    if (res.success) {
      stats.value = res.data
    }
  } catch {
    statsVisible.value = false
  }
}

function showResetDialog(row) {
  resetForm.userId = row.user_id
  resetForm.username = row.username
  resetForm.newPassword = ''
  resetVisible.value = true
}

async function doResetPassword() {
  if (resetForm.newPassword.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  resetLoading.value = true
  try {
    const res = await resetUserPassword(resetForm.userId, resetForm.newPassword)
    if (res.success) {
      ElMessage.success('密码已重置')
      resetVisible.value = false
    } else {
      ElMessage.error(res.error?.message || '重置失败')
    }
  } catch {
    // handled by interceptor
  } finally {
    resetLoading.value = false
  }
}

async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除用户「${row.username}」吗？其历史数据会被保留但脱敏。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    const res = await deleteUser(row.user_id)
    if (res.success) {
      ElMessage.success('用户已删除')
      loadUsers()
    } else {
      ElMessage.error(res.error?.message || '删除失败')
    }
  } catch {
    // cancel or error
  }
}

onMounted(loadUsers)
</script>
```

- [ ] **Step 2: 编译验证**

```bash
cd D:\HAJI\web-admin && npm run build
```
Expected: 编译成功。

- [ ] **Step 3: Commit**

```bash
cd D:\HAJI\web-admin
git add src/views/Users.vue
git commit -m "feat: add user management page (list/stats/reset-password/delete)"
```

---

### Task 5: 集成测试 & 修复

**Files:**
- 无新建，整体验证

- [ ] **Step 1: 启动后端 + 开发服务器，端到端测试**

```bash
# Terminal 1: 启动 A 端
cd D:\HAJI\HAJIMI_UI
python -m server.main &

# Terminal 2: 启动前端开发服务器
cd D:\HAJI\web-admin
npm run dev
```

访问 `http://localhost:5173`，做以下测试：

| # | 操作 | 预期 |
|---|------|------|
| 1 | 用 admin/admin 登录 | 跳转 dashboard，header 显示 "admin" |
| 2 | 刷新页面 | 保持登录态 |
| 3 | 点击"用户管理" | 显示用户列表，含分页 |
| 4 | 搜索 "admin" | 只显示 admin 用户 |
| 5 | 点击某用户的"统计" | 抽屉展示统计信息 |
| 6 | 点击"重置密码" → 输入新密码 → 确定 | 提示"密码已重置" |
| 7 | 点击"删除" → 确认 | 提示"用户已删除"，列表刷新 |
| 8 | 点击"退出" | 跳转登录页 |
| 9 | 用错误密码登录 | 提示"用户名或密码错误" |

- [ ] **Step 2: 修复发现的问题**

根据测试结果修复。

- [ ] **Step 3: Commit**

```bash
cd D:\HAJI\web-admin
git add -A
git commit -m "test: integration test passed, login/logout/user CRUD verified"
```

---

## File Summary

| # | File | Action |
|---|------|--------|
| 1 | `src/api/index.js` | Rewrite — token 管理 + 刷新拦截器 |
| 2 | `src/api/admin.js` | Rewrite — 删 Mock，加 auth + users API |
| 3 | `src/main.js` | Modify — 去掉 autoDetectServer |
| 4 | `src/views/Login.vue` | Modify — 对接真实登录 |
| 5 | `src/router/index.js` | Modify — 加 /users 路由，登录页重定向 |
| 6 | `src/components/AppLayout.vue` | Modify — 加菜单项，logout 调 API，显示用户名 |
| 7 | `src/views/Users.vue` | Create — 用户管理页 |
