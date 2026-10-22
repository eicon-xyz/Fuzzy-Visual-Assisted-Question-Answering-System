/**
 * L5 Sidecar API 契约纯逻辑 —— HAJIMI_UI/core/api_client.py 文案与语义 1:1 移植。
 * 实际 HTTP I/O 在 electron/services/sidecarClient.ts。
 */
import { L5_START_HINT } from '../config'

export interface ExecuteBody {
  query: string
  image: string | null
  context: unknown[]
  screen_width: number
  screen_height: number
}

export function buildExecuteBody(
  query: string,
  size: { w: number; h: number } = { w: 1920, h: 1080 }
): ExecuteBody {
  return {
    query,
    image: null,
    context: [],
    screen_width: size.w,
    screen_height: size.h
  }
}

/** _read_http_error：从 HTTP 错误体提取可展示消息（detail 或 error.message，截 300）。 */
export function extractHttpError(bodyText: string, fallback: string): string {
  try {
    const data = JSON.parse(bodyText) as Record<string, unknown>
    if (data && typeof data === 'object') {
      const detail = data.detail ?? (data.error as Record<string, unknown> | undefined)?.message
      if (detail) return String(detail).slice(0, 300)
    }
  } catch {
    /* 非 JSON 体 */
  }
  return bodyText.slice(0, 300) || fallback
}

/** HTTP 状态 → ApiError 文案（401 特判，对齐 Python 版）。 */
export function apiErrorMessage(status: number, bodyText: string): string {
  if (status === 401) return 'X-Demo-Key 不匹配，请检查 HAJIMI_DEMO_KEY'
  return `L5 Sidecar HTTP ${status}: ${extractHttpError(bodyText, '')}`
}

export interface ExecuteValidation {
  ok: boolean
  taskId?: string
  error?: string
}

/** execute_task 返回校验：success 旗标 + task_id（错误优先级同 Python 版）。 */
export function validateExecuteResponse(data: Record<string, unknown>): ExecuteValidation {
  if (!data.success) {
    const err = data.error
    const msg =
      err && typeof err === 'object'
        ? String((err as Record<string, unknown>).message || 'L5 执行提交失败')
        : 'L5 执行提交失败'
    return { ok: false, error: msg }
  }
  if (!data.task_id) return { ok: false, error: 'L5 Sidecar 未返回 task_id' }
  return { ok: true, taskId: String(data.task_id) }
}

export interface HealthPayload {
  status?: string
  message?: string
  degraded?: boolean
  [k: string]: unknown
}

export function healthIsUsable(live: HealthPayload | null): boolean {
  return !!live && (live.status === 'ok' || live.status === 'degraded')
}

export interface StatusText {
  text: string
  kind: 'system ok' | 'system warn' | 'system danger'
}

/** get_api_status_message 文案移植（含降级与未启动提示）。 */
export function statusTextFromHealth(
  live: HealthPayload | null,
  port: number | string = 8011
): StatusText {
  if (live && live.status === 'ok') {
    return { text: `L5 自动执行就绪 (Sidecar :${port})`, kind: 'system ok' }
  }
  if (live && (live.status === 'degraded' || live.status === 'warn')) {
    const msg = live.message || 'Sidecar 降级：模型未完全就绪'
    return { text: `L5 Sidecar 降级 — ${msg}`, kind: 'system warn' }
  }
  return {
    text: `L5 Sidecar 未启动 (:${port})。请运行 ${L5_START_HINT}`,
    kind: 'system danger'
  }
}
