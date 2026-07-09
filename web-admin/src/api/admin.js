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
  const res = await api.get('/admin/flow/topology')
  return res.success ? res.data : res
}

export async function fetchFlowMetrics(apiPath = '/api/demo/process', range = '1h') {
  const res = await api.get('/admin/flow/metrics', { params: { api_path: apiPath, range } })
  return res.success ? res.data : res
}

export async function fetchFlowVersions() {
  const res = await api.get('/admin/flow/versions')
  return res.success ? res.data : res
}

export async function fetchMonitorHealth() {
  const res = await api.get('/admin/monitor/health')
  return res.success ? res.data : res
}

export async function fetchAlerts(params = {}) {
  const res = await api.get('/admin/monitor/alerts', { params })
  return res.success ? res.data : res
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
  const res = await api.get('/admin/config/deploy-logs', { params: { limit } })
  return res.success ? res.data : res
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
