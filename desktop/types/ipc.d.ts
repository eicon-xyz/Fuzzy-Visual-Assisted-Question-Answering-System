/**
 * 渲染层可见的桥 API 类型（preload 与 src 共用，防契约漂移）。
 */
export interface SubmitResult {
  ok: boolean
  taskId?: string
  normalized?: string
  consentDeclined?: boolean
  error?: string
}

export interface TaskEventPayload {
  taskId?: string
  /** Sidecar SSE 事件名 + 本地注入的 _submitted / _stream_error */
  event: string
  data: unknown
}

export interface SidecarStatePayload {
  phase: 'running' | 'starting' | 'spawned' | 'missing' | 'failed' | 'down'
  detail: string
}

export interface SettingsSnapshot {
  ui_theme?: string
  font_size?: number
  demo_key?: string
  l5_consent_accepted?: boolean
  l5_desktop_overlay?: boolean
  shortcut_l5_approve?: string
  shortcut_l5_stop?: string
  shortcut_l5_pause?: string
  proxy_enabled?: boolean
  http_proxy?: string
  https_proxy?: string
  llm?: { base_url?: string; api_key?: string; model?: string }
  voice?: { tts_enabled?: boolean; [k: string]: unknown }
  [k: string]: unknown
}

export interface SaveResult {
  ok: boolean
  envSyncedTo?: string
  error?: string
}

export interface AuthStatus {
  valid: boolean
  username: string
}

export interface HajimiApi {
  getVersion: () => Promise<string>
  platform: () => NodeJS.Platform
  taskSubmit: (
    query: string,
    acceptConsent: boolean,
    dontShowAgain?: boolean
  ) => Promise<SubmitResult>
  taskCancel: () => Promise<{ ok: boolean; error?: string }>
  sidecarStatus: () => Promise<{ ok: boolean; detail: string }>
  consentAccepted: () => Promise<boolean>
  settingsGet: () => Promise<SettingsSnapshot>
  settingsSave: (fragment: SettingsSnapshot) => Promise<SaveResult>
  authStatus: () => Promise<AuthStatus>
  authLogin: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>
  authLogout: () => Promise<{ ok: boolean }>
  windowSetCompact: (compact: boolean) => Promise<{ ok: boolean; compact: boolean }>
  windowGetMode: () => Promise<{ compact: boolean }>
  onWindowMode: (cb: (p: { compact: boolean }) => void) => () => void
  onTaskEvent: (cb: (p: TaskEventPayload) => void) => () => void
  onSidecarState: (cb: (p: SidecarStatePayload) => void) => () => void
}

declare global {
  interface Window {
    hajimi: HajimiApi
  }
}

export {}
