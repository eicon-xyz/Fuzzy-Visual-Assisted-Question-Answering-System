import axios from 'axios'
import { ElMessage } from 'element-plus'
import {
  AUTH_REFRESH_ON_401,
  clearSession,
  getAccessToken,
  refresh,
} from './auth'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

const DEMO_KEY = 'hajimi-demo-2026'

function isAuthPath(url = '') {
  return url.startsWith('/auth') || url.includes('/auth/')
}

// 请求拦截：业务 API 仍带 Demo Key；/auth 不带 Key
api.interceptors.request.use((config) => {
  const url = config.url || ''
  if (!isAuthPath(url)) {
    if (url.startsWith('/admin') || url.includes('/admin/')) {
      config.headers['X-Admin-Key'] = DEMO_KEY
    } else if (url.startsWith('/audit') || url.startsWith('/config')) {
      config.headers['X-Demo-Key'] = DEMO_KEY
    } else {
      config.headers['X-Demo-Key'] = DEMO_KEY
    }
  }
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise = null

async function tryRefreshAndRetry(failedConfig) {
  if (!AUTH_REFRESH_ON_401) {
    return null
  }
  if (!refreshPromise) {
    refreshPromise = refresh()
      .then(() => {
        refreshPromise = null
      })
      .catch((err) => {
        refreshPromise = null
        throw err
      })
  }
  try {
    await refreshPromise
  } catch {
    return null
  }
  const token = getAccessToken()
  if (!token) return null
  failedConfig.headers = failedConfig.headers || {}
  failedConfig.headers.Authorization = `Bearer ${token}`
  return api.request(failedConfig)
}

api.interceptors.response.use(
  (res) => res.data,
  async (err) => {
    const status = err.response?.status
    const config = err.config || {}
    const url = config.url || ''

    if (status === 401 && !isAuthPath(url)) {
      if (AUTH_REFRESH_ON_401 && !config._authRetried) {
        config._authRetried = true
        const retried = await tryRefreshAndRetry(config)
        if (retried) return retried
      }
      clearSession()
      window.location.hash = '#/login'
      return Promise.reject(err)
    }

    ElMessage.error(err.response?.data?.error?.message || err.message)
    return Promise.reject(err)
  },
)

export default api
