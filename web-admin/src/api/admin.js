/**
 * HAJIMI Admin API 服务层
 * ========================
 * 封装全部 /api/admin/* 端点调用，内置 Mock 数据降级。
 * A 端就位后自动切换真实数据，无需修改页面代码。
 */
import api from './index'

// ═══════════════════════════════════════════
//  Mock 数据（A 端未就位时使用）
// ═══════════════════════════════════════════

const MOCK = {
  overview: {
    today_volume: 1247, volume_change_pct: 12,
    online_clients: 42, overall_useful_rate: 0.89,
    overall_fail_rate: 0.032, monthly_api_cost_usd: 96.50,
  },
  trend: (metric) => {
    const hours = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`)
    if (metric === 'latency') {
      return {
        metric: 'latency', granularity: '1h', unit: 'seconds',
        data: hours.map(h => ({ hour: h, value: parseFloat((1.5 + Math.random() * 5).toFixed(1)) })),
        baselines: { l2_threshold_s: 3.0, l3_threshold_s: 10.0 },
      }
    }
    return {
      metric: 'volume', granularity: '1h',
      data: hours.map(h => ({ hour: h, value: (parseInt(h) >= 8 && parseInt(h) < 18) ? 30 + Math.floor(Math.random() * 90) : 3 + Math.floor(Math.random() * 18) })),
      peak: { hour: '12:00', value: 110 },
    }
  },
  feedback: {
    feedback_distribution: { useful: 89, useless: 6, neutral: 5 },
    route_distribution: { l2: 70, l3: 30 },
    total_feedback_count: 1247,
  },
  topTasks: {
    tasks: [
      { rank: 1, name: 'VSCode 编辑文件', count: 245, route_l2_pct: 78 },
      { rank: 2, name: 'Chrome 浏览网页', count: 198, route_l2_pct: 92 },
      { rank: 3, name: 'Word 编辑文档', count: 156, route_l2_pct: 85 },
      { rank: 4, name: '微信安装', count: 134, route_l2_pct: 45 },
      { rank: 5, name: '系统设置调整', count: 112, route_l2_pct: 67 },
    ],
  },
  redline: {
    redlines: [
      { type: '自动点击请求', count: 67, last_triggered: '2026-06-29T14:20:00Z' },
      { type: '扫描硬盘请求', count: 45, last_triggered: '2026-06-29T13:15:00Z' },
      { type: '系统命令注入', count: 32, last_triggered: '2026-06-29T12:40:00Z' },
    ],
  },
  failures: {
    stats: {
      distribution: [
        { type: 'blueprint_mismatch', label: '蓝图不匹配', count: 48 },
        { type: 'llm_timeout', label: 'LLM 超时', count: 32 },
        { type: 'parse_error', label: '解析错误', count: 28 },
        { type: 'redline_blocked', label: '红线拦截', count: 25 },
        { type: 'user_abort', label: '用户中止', count: 23 },
      ],
      trend: Array.from({ length: 24 }, (_, i) => ({ hour: `${i}:00`, count: Math.floor(Math.random() * 25 + 5) })),
      total: 156,
    },
    list: (cursor) => ({
      items: Array.from({ length: 5 }, (_, i) => ({
        id: `fail_${(parseInt(cursor || '0') + i).toString().padStart(3, '0')}`,
        task_id: `550e8400-${i}`,
        timestamp: `2026-06-29 ${14 - i}:${20 + i}:10`,
        task_name: ['打开 VSCode', '安装微信', '查找设置', '自动抢票', '修改注册表'][i],
        failed_step: i + 1,
        error_type: ['蓝图不匹配', 'LLM超时', '解析错误', '红线拦截', '用户中止'][i],
        error_summary: ['verb 不匹配', '30s 超时', 'JSON 解析失败', '关键词拦截', '用户手动中止'][i],
        route: i % 2 ? 'L3' : 'L2',
      })),
      next_cursor: String(parseInt(cursor || '0') + 5),
      has_more: parseInt(cursor || '0') < 15,
      total: 20,
    }),
  },
  flow: {
    topology: {
      nodes: [
        { id: 'c12a', label: '客户端 #c12a', type: 'client', online: true },
        { id: 'd07f', label: '客户端 #d07f', type: 'client', online: true },
        { id: 'e3b8', label: '客户端 #e3b8', type: 'client', online: true },
        { id: 'gateway', label: 'HAJIMI Gateway', type: 'server' },
        { id: 'postgres', label: 'PostgreSQL', type: 'database' },
        { id: 'llm', label: 'LLM API (GPT-4)', type: 'external' },
      ],
      links: [
        { source: 'c12a', target: 'gateway', qps: 12, latency_ms: 45, status: 'healthy' },
        { source: 'd07f', target: 'gateway', qps: 8, latency_ms: 52, status: 'healthy' },
        { source: 'e3b8', target: 'gateway', qps: 6, latency_ms: 38, status: 'healthy' },
        { source: 'gateway', target: 'postgres', qps: 30, latency_ms: 12, status: 'healthy' },
        { source: 'gateway', target: 'llm', qps: 8, latency_ms: 4200, status: 'high_load' },
      ],
    },
    metrics: {
      api_path: '/api/demo/process',
      granularity: '5m',
      data: Array.from({ length: 24 }, (_, i) => ({
        time: `${String(i).padStart(2, '0')}:00`,
        qps: 20 + Math.floor(Math.random() * 40),
        success_rate: parseFloat((98 + Math.random() * 2).toFixed(3)),
      })),
    },
    versions: {
      versions: [
        { version: 'v2.1.0', count: 34, pct: 80.9 },
        { version: 'v2.0.5', count: 6, pct: 14.3 },
        { version: 'v1.9.0', count: 2, pct: 4.8 },
      ],
      total_clients: 42,
    },
  },
  monitor: {
    health: {
      resources: { cpu_pct: 42, memory_gb: 3.2, disk_free_gb: 128, uptime: '14d 7h 23m', uptime_seconds: 1234567 },
      components: [
        { name: 'PostgreSQL', status: 'healthy', detail: '连接池 8/20' },
        { name: 'Redis', status: 'healthy', detail: '命中率 94%' },
        { name: 'LLM API', status: 'degraded', detail: '平均延迟 4.2s（超阈值 3s）' },
        { name: 'Nginx', status: 'healthy', detail: 'QPS 120' },
      ],
    },
    alerts: {
      alerts: [
        { id: 'alert_001', timestamp: '2026-06-29T14:20:33Z', level: 'warning', message: 'LLM API 平均延迟 4.2s 超过阈值 3s，持续 15 分钟', status: 'unread' },
        { id: 'alert_002', timestamp: '2026-06-29T13:45:00Z', level: 'warning', message: '客户端 #d07f 离线超过 30 分钟', status: 'read' },
        { id: 'alert_003', timestamp: '2026-06-29T11:10:00Z', level: 'error', message: 'PostgreSQL 连接池耗尽 (20/20)', status: 'unread' },
      ],
      total_unread: 2, total: 3,
    },
  },
  config: {
    current: {
      config: {
        version: 'v2.1.3',
        confidence_threshold: 80,
        llm_api_endpoint: 'https://api.openai.com/v1',
        llm_model: 'gpt-4o',
        template_similarity_threshold: 90,
        max_blueprint_steps: 15,
        token_limit: 8000,
        config_pull_interval_min: 30,
        audit_batch_size: 10,
        offline_tts_engine: 'pyttsx3',
        routing_rules: { length_weight: 0.3, verb_weight: 8, cross_app_bonus: 10, threshold_score: 30, custom_keywords: ['安装', '配置', '设置'] },
        updated_at: '2026-06-29T12:00:00Z',
      },
      deployed_at: '2026-06-29T11:00:00Z',
      deployed_by: 'admin@hajimi.local',
    },
  },
}

// ═══════════════════════════════════════════
//  USE_MOCK 开关：A 端未就位时为 true
// ═══════════════════════════════════════════

let USE_MOCK = true

export function setUseMock(v) { USE_MOCK = v }
export function isMockMode() { return USE_MOCK }

// ═══════════════════════════════════════════
//  API 方法
// ═══════════════════════════════════════════

function delay(ms = 200) {
  return new Promise(r => setTimeout(r, USE_MOCK ? ms : 0))
}

/** 总览 — KPI 卡片 */
export async function fetchOverview(range = '24h') {
  await delay()
  if (USE_MOCK) return MOCK.overview
  return api.get('/admin/stats/overview', { params: { range } })
}

/** 总览 — 24h 趋势 (volume | latency) */
export async function fetchTrend(metric = 'volume', range = '24h') {
  await delay()
  if (USE_MOCK) return MOCK.trend(metric)
  return api.get('/admin/stats/trend', { params: { metric, range } })
}

/** 总览 — 反馈 + L2/L3 分布 */
export async function fetchFeedback() {
  await delay()
  if (USE_MOCK) return MOCK.feedback
  return api.get('/admin/stats/feedback')
}

/** 总览 — 高频任务 TOP N */
export async function fetchTopTasks(limit = 10, range = '7d') {
  await delay()
  if (USE_MOCK) return MOCK.topTasks
  return api.get('/admin/stats/top-tasks', { params: { limit, range } })
}

/** 总览 — 红线拦截 */
export async function fetchRedline(limit = 5) {
  await delay()
  if (USE_MOCK) return MOCK.redline
  return api.get('/admin/stats/redline', { params: { limit } })
}

/** 失败归因 — 统计 */
export async function fetchFailuresStats(params = {}) {
  await delay()
  if (USE_MOCK) return MOCK.failures.stats
  return api.get('/admin/failures/stats', { params })
}

/** 失败归因 — 列表（游标分页） */
export async function fetchFailuresList(params = {}) {
  await delay()
  if (USE_MOCK) return MOCK.failures.list(params.cursor || '0')
  return api.get('/admin/failures/list', { params })
}

/** 失败归因 — 单条详情 */
export async function fetchFailureDetail(taskId) {
  await delay()
  if (USE_MOCK) return {}
  return api.get(`/admin/failures/detail/${taskId}`)
}

/** 数据流 — 拓扑 */
export async function fetchFlowTopology() {
  await delay()
  if (USE_MOCK) return MOCK.flow.topology
  return api.get('/admin/flow/topology')
}

/** 数据流 — QPS/成功率 */
export async function fetchFlowMetrics(apiPath = '/api/demo/process', range = '1h') {
  await delay()
  if (USE_MOCK) return MOCK.flow.metrics
  return api.get('/admin/flow/metrics', { params: { api_path: apiPath, range } })
}

/** 数据流 — 版本分布 */
export async function fetchFlowVersions() {
  await delay()
  if (USE_MOCK) return MOCK.flow.versions
  return api.get('/admin/flow/versions')
}

/** 健康 — 组件状态 */
export async function fetchMonitorHealth() {
  await delay()
  if (USE_MOCK) return MOCK.monitor.health
  return api.get('/admin/monitor/health')
}

/** 健康 — 告警列表 */
export async function fetchAlerts(params = {}) {
  await delay()
  if (USE_MOCK) return MOCK.monitor.alerts
  return api.get('/admin/monitor/alerts', { params })
}

/** 健康 — 标记告警已读 */
export async function markAlertRead(alertId) {
  if (USE_MOCK) return { marked_read: 1 }
  return api.post(`/admin/monitor/alerts/${alertId}/read`)
}

/** 健康 — 全部已读 */
export async function markAllAlertsRead() {
  if (USE_MOCK) return { marked_read: 99 }
  return api.post('/admin/monitor/alerts/read-all')
}

/** 配置 — 获取当前 */
export async function fetchConfigCurrent() {
  await delay()
  if (USE_MOCK) return MOCK.config.current
  return api.get('/admin/config/current')
}

/** 配置 — 热部署 */
export async function deployConfig(config) {
  if (USE_MOCK) {
    await delay(800)
    return { deployed: true, version: 'v2.1.4', affected_clients: 42, deployed_at: new Date().toISOString() }
  }
  return api.post('/admin/config/deploy', { config })
}

/** 配置 — 部署操作日志 */
export async function fetchDeployLogs(limit = 20) {
  await delay()
  if (USE_MOCK) {
    return {
      logs: [
        { id: 1, operator: 'admin@hajimi.local', version: 'v2.1.3', action: 'deploy', timestamp: '2026-06-29T11:00:00Z', affected: 42 },
        { id: 2, operator: 'admin@hajimi.local', version: 'v2.1.2', action: 'deploy', timestamp: '2026-06-28T15:00:00Z', affected: 40 },
        { id: 3, operator: 'admin@hajimi.local', version: 'v2.1.1', action: 'rollback', timestamp: '2026-06-28T14:30:00Z', affected: 40 },
      ],
    }
  }
  return api.get('/admin/config/deploy-logs', { params: { limit } })
}

// ═══════════════════════════════════════════
//  GPU OmniParser 监控 (B端 GPU API)
//  对应 B端-OmniParser-GPU-API部署文档 §六
// ═══════════════════════════════════════════

const GPU_API_URL = 'http://10.0.0.5:9800'  // 校园网 GPU 服务器，按实际 IP 修改

/** GPU 健康检查 */
export async function fetchGpuHealth() {
  try {
    const res = await fetch(`${GPU_API_URL}/health`, { signal: AbortSignal.timeout(5000) })
    return await res.json()
  } catch {
    return null
  }
}

/** GPU 详细探测 (含显存) */
export async function fetchGpuProbe() {
  try {
    const res = await fetch(`${GPU_API_URL}/probe/`, { signal: AbortSignal.timeout(5000) })
    return await res.json()
  } catch {
    return null
  }
}

export default {
  setUseMock, isMockMode,
  fetchOverview, fetchTrend, fetchFeedback, fetchTopTasks, fetchRedline,
  fetchFailuresStats, fetchFailuresList, fetchFailureDetail,
  fetchFlowTopology, fetchFlowMetrics, fetchFlowVersions,
  fetchMonitorHealth, fetchAlerts, markAlertRead, markAllAlertsRead,
  fetchConfigCurrent, deployConfig, fetchDeployLogs,
  fetchGpuHealth, fetchGpuProbe,
}
