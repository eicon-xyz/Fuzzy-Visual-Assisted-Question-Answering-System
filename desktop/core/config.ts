/**
 * 桌面端运行配置 —— 对齐 HAJIMI_UI/config.py + core/defaults.py 的 env 口径。
 * （M2 起 user_settings.json 中的对应字段会以更高优先级合入。）
 */

export const DEFAULT_L5_HOST = '127.0.0.1'
export const DEFAULT_L5_PORT = 8011
export const DEFAULT_DEMO_KEY = 'hajimi-demo-2026'

export interface DesktopConfig {
  apiBaseUrl: string
  demoKey: string
  /** HTTP 常规请求超时（ms），对齐 API_TIMEOUT=30s */
  apiTimeoutMs: number
  /** /execute 长超时（ms），对齐 HAJIMI_EXECUTE_TIMEOUT=360s */
  executeTimeoutMs: number
  /** health 探测超时（ms），对齐 HEALTH_TIMEOUT=5s */
  healthTimeoutMs: number
  /** 退出时是否杀掉自己拉起的 Sidecar（HAJIMI_STOP_SERVICES_ON_EXIT） */
  stopServicesOnExit: boolean
  /** 跳过登录（HAJIMI_SKIP_LOGIN） */
  skipLogin: boolean
  /** Sidecar 根目录覆盖（HAJIMI_L5_ROOT） */
  l5RootOverride: string
}

type Env = Record<string, string | undefined>

function truthy(v: string | undefined, dflt: boolean): boolean {
  if (v === undefined || v === '') return dflt
  return ['1', 'true', 'yes'].includes(v.trim().toLowerCase())
}

export function configFromEnv(env: Env = process.env as Env): DesktopConfig {
  const explicit = (env.L5_API_URL || '').trim().replace(/\/+$/, '')
  const host = (env.L5_API_HOST || DEFAULT_L5_HOST).trim()
  const port = (env.L5_API_PORT || String(DEFAULT_L5_PORT)).trim()
  return {
    apiBaseUrl: explicit || `http://${host}:${port}`,
    demoKey: (env.HAJIMI_DEMO_KEY || DEFAULT_DEMO_KEY).trim(),
    apiTimeoutMs: 30_000,
    executeTimeoutMs: (Number(env.HAJIMI_EXECUTE_TIMEOUT) || 360) * 1000,
    healthTimeoutMs: 5_000,
    stopServicesOnExit: truthy(env.HAJIMI_STOP_SERVICES_ON_EXIT, true),
    skipLogin: truthy(env.HAJIMI_SKIP_LOGIN, false),
    l5RootOverride: (env.HAJIMI_L5_ROOT || '').trim()
  }
}

export const L5_START_HINT =
  'HAJIMI_UI\\scripts\\start_l5_sidecar.bat'
