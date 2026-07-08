import { getAccessToken, getUser, migrateLegacyToken } from './storage'

export function isAuthenticated() {
  migrateLegacyToken()
  return Boolean(getAccessToken())
}

export function getUsername() {
  const user = getUser()
  if (user?.username) return user.username
  return 'admin'
}

export function getRole() {
  const user = getUser()
  return user?.role || 'admin'
}
