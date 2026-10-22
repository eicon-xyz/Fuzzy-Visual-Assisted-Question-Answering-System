import { describe, expect, it } from 'vitest'
import {
  apiErrorMessage,
  buildExecuteBody,
  healthIsUsable,
  statusTextFromHealth,
  validateExecuteResponse
} from './contract'

describe('buildExecuteBody（ProcessRequest 契约）', () => {
  it('L5 提交体字段齐全', () => {
    expect(buildExecuteBody('打开记事本')).toEqual({
      query: '打开记事本',
      image: null,
      context: [],
      screen_width: 1920,
      screen_height: 1080
    })
  })
})

describe('错误文案（api_client.py 对齐）', () => {
  it('401 特判', () => {
    expect(apiErrorMessage(401, '{}')).toBe('X-Demo-Key 不匹配，请检查 HAJIMI_DEMO_KEY')
  })
  it('detail 结构提取', () => {
    const body = JSON.stringify({ detail: { code: 'REDLINE', message: '' } })
    expect(apiErrorMessage(400, body)).toContain('HTTP 400')
  })
  it('error.message 提取', () => {
    const body = JSON.stringify({ detail: '规划失败' })
    expect(apiErrorMessage(500, body)).toBe('L5 Sidecar HTTP 500: 规划失败')
  })
})

describe('validateExecuteResponse', () => {
  it('success=false → error.message', () => {
    expect(
      validateExecuteResponse({ success: false, error: { message: 'REDLINE 拦截' } })
    ).toEqual({ ok: false, error: 'REDLINE 拦截' })
  })
  it('缺 task_id → 专用文案', () => {
    expect(validateExecuteResponse({ success: true })).toEqual({
      ok: false,
      error: 'L5 Sidecar 未返回 task_id'
    })
  })
  it('正常路径', () => {
    expect(validateExecuteResponse({ success: true, task_id: 't1' })).toEqual({
      ok: true,
      taskId: 't1'
    })
  })
})

describe('health 状态文案（get_api_status_message 对齐）', () => {
  it('ok', () => {
    const s = statusTextFromHealth({ status: 'ok' }, 8011)
    expect(s.text).toBe('L5 自动执行就绪 (Sidecar :8011)')
    expect(s.kind).toBe('system ok')
  })
  it('degraded 带消息', () => {
    const s = statusTextFromHealth({ status: 'degraded', message: '模型未就绪' })
    expect(s.text).toBe('L5 Sidecar 降级 — 模型未就绪')
    expect(s.kind).toBe('system warn')
  })
  it('null → 未启动 hint', () => {
    const s = statusTextFromHealth(null)
    expect(s.kind).toBe('system danger')
    expect(s.text).toContain('start_l5_sidecar.bat')
  })
  it('healthIsUsable 接受 ok/degraded', () => {
    expect(healthIsUsable({ status: 'ok' })).toBe(true)
    expect(healthIsUsable({ status: 'degraded' })).toBe(true)
    expect(healthIsUsable(null)).toBe(false)
  })
})
