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
