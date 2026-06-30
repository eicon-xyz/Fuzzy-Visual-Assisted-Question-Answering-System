import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// 请求拦截：携带 JWT
api.interceptors.request.use((config) => {
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
