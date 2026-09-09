/**
 * HAJIMI Admin API 服务层
 * 全部 /api/admin/* 端点，真实 API 调用。
 * 后端为 L5 Sidecar（server_A，:8011），经 vite proxy 转发；见 vite.config.js。
 */
import api from './index'

// ═══════════════════════════════════════════
//  认证 API
// ═══════════════════════════════════════════

export async function authLogin(username, password) {
  return api.post('/auth/login', { username, password })
}

// 注：/auth/register、/auth/refresh、/auth/logout 在 L5 Sidecar 中均未实现
// （refresh 原属已删除的旧 A 端 :8010），登出改为仅清理本地会话（AppLayout.vue）。

// ═══════════════════════════════════════════
//  用户管理 API
// ═══════════════════════════════════════════
// 以下 4 个端点原由已删除的旧 A 端（HAJIMI_UI/server，:8010）提供，
// L5 Sidecar（server_A）尚未移植 users 路由，当前会返回 404。
// 保留待 server_A 补齐；Users.vue 会捕获异常，但响应拦截器仍会弹一次错误提示。

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

// 注：原 fetchFailuresStats() → GET /admin/failures/stats 已删除：
// 该端点在新旧后端都不存在，且无任何视图引用（失败统计请由 list 汇总）。

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

export async function fetchFlowMetrics(apiPath = '/api/demo/execute', range = '1h') {
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

// 注：Sidecar 只实现 POST /admin/monitor/alerts/read-all，
// 单条已读端点 POST /admin/monitor/alerts/{id}/read 尚缺（HealthMonitor 点击「已读」会 404）。
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

// 注：原「GPU OmniParser 监控」(:9800 直连 /health、/probe/) 属 L4 指引模式链路，
// 已随 L4 移除；健康状态统一走 /api/admin/monitor/health。
