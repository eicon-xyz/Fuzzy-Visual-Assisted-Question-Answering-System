/**
 * B 端登录会话纯逻辑 —— HAJIMI_UI/core/auth_session.py 移植（无 electron/HTTP 依赖）。
 * 文件读写与 fetch 在 electron/services/authSession.ts；本文件锁定语义可测。
 */

export const DEFAULT_DEMO_USERNAME = 'admin'
export const DEFAULT_DEMO_PASSWORD = 'demo123'
export const LOCAL_DEMO_TOKEN_PREFIX = 'local-demo.'
export const LOCAL_DEMO_EXPIRES_SEC = 7200

export interface Session {
  access_token: string
  refresh_token?: string | null
  user: { username: string; role?: string }
  username?: string
  expires_at: number
  local_demo?: boolean
}

/** normalize_login_response：success 包裹 或 平铺 token 两种响应形。 */
export function normalizeLoginResponse(
  raw: Record<string, unknown>,
  fallbackUsername = ''
): { access_token: string; refresh_token?: string | null; user: Record<string, unknown>; expires_in: number } {
  if (raw.success === true && raw.data && typeof raw.data === 'object') {
    const data = raw.data as Record<string, unknown>
    return {
      access_token: String(data.access_token ?? ''),
      refresh_token: (data.refresh_token as string | null | undefined) ?? null,
      user: (data.user as Record<string, unknown>) ?? { username: fallbackUsername, role: 'admin' },
      expires_in: Number(data.expires_in ?? 1800) || 1800
    }
  }
  if (raw.access_token) {
    return {
      access_token: String(raw.access_token),
      refresh_token: (raw.refresh_token as string | null | undefined) ?? null,
      user: (raw.user as Record<string, unknown>) ?? { username: fallbackUsername, role: 'admin' },
      expires_in: Number(raw.expires_in ?? 7200) || 7200
    }
  }
  throw new Error('登录响应缺少 access_token')
}

/** is_session_valid：无 token 无效；无 expires_at 视为有效（对齐 Python）。 */
export function isSessionValid(
  session: Partial<Session> | null,
  nowSec = Date.now() / 1000
): boolean {
  if (!session || !session.access_token) return false
  if (session.expires_at === undefined || session.expires_at === null) return true
  const exp = Number(session.expires_at)
  if (Number.isNaN(exp)) return false
  return exp > nowSec
}

export function isDemoCredentials(username: string, password: string): boolean {
  return username.trim() === DEFAULT_DEMO_USERNAME && password === DEFAULT_DEMO_PASSWORD
}

export function createLocalDemoSession(username: string, nowSec = Date.now() / 1000): Session {
  return {
    access_token: `${LOCAL_DEMO_TOKEN_PREFIX}${Math.floor(nowSec)}`,
    refresh_token: null,
    user: { username, role: 'admin' },
    username,
    expires_at: nowSec + LOCAL_DEMO_EXPIRES_SEC,
    local_demo: true
  }
}

/** _read_http_error：登录失败可展示消息提取。 */
export function extractLoginError(bodyText: string, statusCode: number): string {
  try {
    const data = JSON.parse(bodyText) as Record<string, unknown>
    const detail = data.detail
    if (detail && typeof detail === 'object') {
      const err = (detail as Record<string, unknown>).error ?? detail
      if (err && typeof err === 'object' && (err as Record<string, unknown>).message) {
        return String((err as Record<string, unknown>).message)
      }
    }
    if (typeof detail === 'string') return detail
    const em = (data.error as Record<string, unknown> | undefined)?.message
    if (em) return String(em)
    return bodyText.slice(0, 200) || `HTTP ${statusCode}`
  } catch {
    return `HTTP ${statusCode}`
  }
}
