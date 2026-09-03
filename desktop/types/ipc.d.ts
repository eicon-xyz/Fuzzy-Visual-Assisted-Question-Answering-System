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
  onTaskEvent: (cb: (p: TaskEventPayload) => void) => () => void
  onSidecarState: (cb: (p: SidecarStatePayload) => void) => () => void
}

declare global {
  interface Window {
    hajimi: HajimiApi
  }
}

export {}
