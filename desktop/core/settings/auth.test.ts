import { describe, expect, it } from 'vitest'
import {
  createLocalDemoSession,
  extractLoginError,
  isDemoCredentials,
  isSessionValid,
  normalizeLoginResponse
} from './auth'

describe('auth_session.py 语义移植', () => {
  it('normalizeLoginResponse 两形响应', () => {
    expect(
      normalizeLoginResponse({ success: true, data: { access_token: 'a', expires_in: 10 } }, 'u').access_token
    ).toBe('a')
    expect(normalizeLoginResponse({ access_token: 'b' }, 'u').expires_in).toBe(7200)
    expect(() => normalizeLoginResponse({ foo: 1 })).toThrow('登录响应缺少 access_token')
  })

  it('isSessionValid：过期/缺失/无期限', () => {
    const now = 1000
    expect(isSessionValid(null, now)).toBe(false)
    expect(isSessionValid({ access_token: '', expires_at: 2000 }, now)).toBe(false)
    expect(isSessionValid({ access_token: 'a', expires_at: 900 }, now)).toBe(false)
    expect(isSessionValid({ access_token: 'a', expires_at: 1100 }, now)).toBe(true)
    expect(isSessionValid({ access_token: 'a' } as never, now)).toBe(true)
    expect(isSessionValid({ access_token: 'a', expires_at: 'bad' as unknown as number }, now)).toBe(false)
  })

  it('demo 凭据与离线会话', () => {
    expect(isDemoCredentials(' admin ', 'demo123')).toBe(true)
    expect(isDemoCredentials('admin', 'x')).toBe(false)
    const s = createLocalDemoSession('admin', 1234)
    expect(s.access_token).toBe('local-demo.1234')
    expect(s.expires_at).toBe(1234 + 7200)
    expect(s.local_demo).toBe(true)
  })

  it('extractLoginError 优先级', () => {
    expect(extractLoginError(JSON.stringify({ detail: { error: { message: '用户名或密码错误' } } }), 401)).toBe(
      '用户名或密码错误'
    )
    expect(extractLoginError(JSON.stringify({ detail: 'nope' }), 400)).toBe('nope')
    expect(extractLoginError('html...', 502)).toBe('HTTP 502')
  })
})
