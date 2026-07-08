/** Auth storage keys — aligned with api-auth.md target; legacy migrated on read. */
export const ACCESS_TOKEN_KEY = 'hajimi_access_token'
export const REFRESH_TOKEN_KEY = 'hajimi_refresh_token'
export const USER_KEY = 'hajimi_user'
export const LEGACY_TOKEN_KEY = 'hajimi_token'

/** Demo phase: admin API still uses X-Admin-Key (see api/index.js). */
export const AUTH_REFRESH_ON_401 =
  import.meta.env.VITE_AUTH_REFRESH_ON_401 === 'true'
