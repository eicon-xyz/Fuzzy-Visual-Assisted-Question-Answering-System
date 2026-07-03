import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

const DEMO_KEY = 'hajimi-demo-2026'

// 请求拦截：自动携带对应认证头
api.interceptors.request.use((config) => {
  const url = config.url || ''
  if (url.startsWith('/admin') || url.includes('/admin/')) {
    config.headers['X-Admin-Key'] = DEMO_KEY
  } else if (url.startsWith('/audit') || url.startsWith('/config')) {
    config.headers['X-Demo-Key'] = DEMO_KEY
  } else {
    config.headers['X-Demo-Key'] = DEMO_KEY  // demo routes
  }
  // 保留 JWT 兼容（未来 A 端实现 /api/auth/login 后切换）
  const token = localStorage.getItem('hajimi_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 → 跳转登录
api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('hajimi_token')
      window.location.hash = '#/login'
    } else {
      ElMessage.error(err.response?.data?.error?.message || err.message)
    }
    return Promise.reject(err)
  },
)

export default api
