/**
 * 用户设置存储（主进程）：与 PyQt 端 core/user_settings.py 同一文件、同一位置
 *   %LOCALAPPDATA%\HAJIMI\user_settings.json（Linux/macOS: ~/.HAJIMI/），
 * 未识别字段透传保留（双端并存期互不破坏）。
 * 保存时联动 envSync 写 server_A/server/.env（空值不覆盖语义），
 * 并可触发 Sidecar 重启使模型 key 生效（对齐 B 端设置保存→重启链路）。
 */
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { mergeSidecarEnv, type SyncInput } from '../../core/settings/envsync'
import { DEFAULT_DEMO_KEY, type DesktopConfig } from '../../core/config'
import type { SidecarManager } from './sidecarManager'

export interface UserSettings {
  ui_theme?: string
  font_size?: number
  shell_alpha_medium?: number
  shell_alpha_compact?: number
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
  voice?: { tts_enabled?: boolean; asr_enabled?: boolean; tts_speed?: number; [k: string]: unknown }
  [k: string]: unknown
}

const DEFAULTS: UserSettings = {
  ui_theme: 'current',
  font_size: 13,
  shell_alpha_medium: 89,
  shell_alpha_compact: 89,
  demo_key: DEFAULT_DEMO_KEY,
  l5_consent_accepted: false,
  l5_desktop_overlay: true,
  shortcut_l5_approve: 'H',
  shortcut_l5_stop: 'J',
  shortcut_l5_pause: 'P',
  llm: { base_url: '', api_key: '', model: 'deepseek-chat' },
  voice: { tts_enabled: true },
  proxy_enabled: false
}

function hajimiDir(): string {
  const base = process.env.LOCALAPPDATA || homedir()
  const dir = join(base, 'HAJIMI')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return dir
}

export function settingsFilePath(): string {
  return join(hajimiDir(), 'user_settings.json')
}

function readRaw(): UserSettings {
  try {
    const parsed = JSON.parse(readFileSync(settingsFilePath(), 'utf-8')) as UserSettings
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function loadSettings(): UserSettings {
  const raw = readRaw()
  return {
    ...DEFAULTS,
    ...raw,
    llm: { ...DEFAULTS.llm, ...(raw.llm ?? {}) },
    voice: { ...(DEFAULTS.voice as object), ...(raw.voice ?? {}) }
  }
}

export interface SaveResult {
  ok: boolean
  envSyncedTo?: string
  error?: string
}

export class SettingsStore {
  constructor(
    private cfg: DesktopConfig,
    private manager: () => SidecarManager,
    /** 打包/开发态定位 server_A/server/.env；找不到返回 null（跳过同步不报错） */
    private envPathResolver: () => string | null
  ) {}

  load(): UserSettings {
    return loadSettings()
  }

  consentAccepted(): boolean {
    return Boolean(this.load().l5_consent_accepted)
  }

  markConsent(dontShowAgain: boolean): void {
    if (dontShowAgain) this.saveFragment({ l5_consent_accepted: true })
  }

  /** save_settings_fragment：浅合并 + llm/voice 深一层合并，原子覆写。 */
  saveFragment(fragment: UserSettings): SaveResult {
    try {
      const cur = readRaw()
      const merged: UserSettings = {
        ...cur,
        ...fragment,
        llm: { ...(cur.llm ?? {}), ...(fragment.llm ?? {}) },
        voice: { ...(cur.voice ?? {}), ...(fragment.voice ?? {}) }
      }
      writeFileSync(settingsFilePath(), JSON.stringify(merged, null, 2), 'utf-8')
      const env = this.syncEnv(merged)
      return { ok: true, envSyncedTo: env ?? undefined }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  }

  /** sync_l5_sidecar_env：合并写 Sidecar .env（空值不覆盖）。 */
  syncEnv(data: UserSettings): string | null {
    const envPath = this.envPathResolver()
    if (!envPath) return null
    try {
      const existing = existsSync(envPath) ? readFileSync(envPath, 'utf-8') : ''
      const input: SyncInput = { demo_key: data.demo_key, llm: data.llm }
      const merged = mergeSidecarEnv(existing, input, {
        demoKey: DEFAULT_DEMO_KEY,
        host: '127.0.0.1',
        port: String(new URL(this.cfg.apiBaseUrl).port || '8011')
      })
      const tmp = envPath + '.desktop.tmp'
      writeFileSync(tmp, merged, 'utf-8')
      renameSync(tmp, envPath)
      return envPath
    } catch {
      return null // 同步失败不阻断设置保存（与 PyQt print-skip 一致）
    }
  }

  /** 设置保存后重启 Sidecar（模型 key 生效），对齐 app_controller 行为。 */
  async restartSidecar(): Promise<void> {
    this.manager().shutdown()
    await this.manager().ensureRunning()
  }
}
