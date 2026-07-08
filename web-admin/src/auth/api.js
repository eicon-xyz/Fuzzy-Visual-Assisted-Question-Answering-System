import axios from 'axios'
import { adaptLoginResponse } from './normalize'
import { clearSession, setSession } from './storage'

/** Auth-only client — no X-Admin-Key / X-Demo-Key. */
const authHttp = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export async function login(username, password) {
  const { data } = await authHttp.post('/auth/login', { username, password })
  const session = adaptLoginResponse(data, username)
  setSession({
    accessToken: session.accessToken,
    refreshToken: session.refreshToken,
    user: session.user,
  })
  return session
}

/** Phase 2: wire POST /api/auth/refresh when A-end implements it. */
export async function refresh() {
  throw new Error('AUTH_REFRESH_NOT_IMPLEMENTED')
}

/** Phase 2: wire POST /api/auth/logout; demo clears local session only. */
export async function logout() {
  clearSession()
}

export function extractErrorMessage(err) {
  const data = err?.response?.data
  if (!data) return err?.message || '登录失败'
  const detail = data.detail
  if (detail?.error?.message) return detail.error.message
  if (typeof detail === 'string') return detail
  if (data.error?.message) return data.error.message
  return err?.message || '登录失败'
}
