/**
 * preload：contextBridge 白名单桥（M1 扩展任务/侧栏/同意 API）。
 */
import { contextBridge, ipcRenderer } from 'electron'
import type { HajimiApi, TaskEventPayload, SidecarStatePayload } from '../types/ipc'

function subscribe<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_e: unknown, payload: T): void => cb(payload)
  ipcRenderer.on(channel, listener)
  return () => ipcRenderer.removeListener(channel, listener)
}

const api: HajimiApi = {
  getVersion: () => ipcRenderer.invoke('app:get-version'),
  platform: () => process.platform,
  taskSubmit: (query: string, acceptConsent: boolean, dontShowAgain?: boolean) =>
    ipcRenderer.invoke('task:submit', { query, acceptConsent, dontShowAgain }),
  taskCancel: () => ipcRenderer.invoke('task:cancel'),
  sidecarStatus: () => ipcRenderer.invoke('sidecar:status'),
  consentAccepted: () => ipcRenderer.invoke('consent:accepted'),
  onTaskEvent: (cb: (p: TaskEventPayload) => void) => subscribe('task:event', cb),
  onSidecarState: (cb: (p: SidecarStatePayload) => void) => subscribe('sidecar:state', cb)
}

contextBridge.exposeInMainWorld('hajimi', api)
