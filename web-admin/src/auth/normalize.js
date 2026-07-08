/**
 * Adapt A-end login responses (stub or future api-auth.md shape) to internal session.
 */
export function adaptLoginResponse(raw, fallbackUsername = '') {
  if (!raw || typeof raw !== 'object') {
    throw new Error('登录响应无效')
  }

  // Future: { success, data: { access_token, refresh_token, user } }
  if (raw.success === true && raw.data) {
    const d = raw.data
    return {
      accessToken: d.access_token || '',
      refreshToken: d.refresh_token || null,
      user: d.user || { username: fallbackUsername, role: 'admin' },
      expiresIn: d.expires_in ?? 1800,
    }
  }

  // Current stub: { access_token, token_type, expires_in }
  if (raw.access_token) {
    return {
      accessToken: raw.access_token,
      refreshToken: raw.refresh_token || null,
      user: raw.user || { username: fallbackUsername, role: 'admin' },
      expiresIn: raw.expires_in ?? 7200,
    }
  }

  throw new Error('登录响应缺少 access_token')
}
