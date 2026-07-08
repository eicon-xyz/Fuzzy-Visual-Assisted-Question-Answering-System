import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  USER_KEY,
  LEGACY_TOKEN_KEY,
} from './constants'

export function getAccessToken() {
  migrateLegacyToken()
  return localStorage.getItem(ACCESS_TOKEN_KEY) || ''
}

export function getRefreshToken() {
  migrateLegacyToken()
  return localStorage.getItem(REFRESH_TOKEN_KEY) || ''
}

export function getUser() {
  migrateLegacyToken()
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function setSession({ accessToken, refreshToken = null, user = null }) {
  if (accessToken) {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  }
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  }
  localStorage.removeItem(LEGACY_TOKEN_KEY)
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(LEGACY_TOKEN_KEY)
}

/** One-time migration from mock login key. */
export function migrateLegacyToken() {
  const legacy = localStorage.getItem(LEGACY_TOKEN_KEY)
  if (!legacy) return
  if (!localStorage.getItem(ACCESS_TOKEN_KEY)) {
    localStorage.setItem(ACCESS_TOKEN_KEY, legacy)
  }
  localStorage.removeItem(LEGACY_TOKEN_KEY)
}
