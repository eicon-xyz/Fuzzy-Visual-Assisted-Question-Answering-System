/**
 * L5 知情确认持久化（M1 独立小文件；M2 并入 user_settings.json 兼容存储）。
 * 对应 PyQt：user_settings.l5_consent_accepted。
 */
import { app } from 'electron'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

interface ConsentFile {
  l5_consent_accepted: boolean
}

function filePath(): string {
  const dir = join(app.getPath('userData'), 'hajimi-desktop')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return join(dir, 'consent.json')
}

export function loadConsent(): ConsentFile {
  try {
    const raw = JSON.parse(readFileSync(filePath(), 'utf-8')) as Partial<ConsentFile>
    return { l5_consent_accepted: Boolean(raw.l5_consent_accepted) }
  } catch {
    return { l5_consent_accepted: false }
  }
}

export function saveConsent(accepted: boolean): void {
  try {
    writeFileSync(filePath(), JSON.stringify({ l5_consent_accepted: accepted }), 'utf-8')
  } catch {
    /* 持久化失败不阻断执行链（下次仍会询问） */
  }
}
