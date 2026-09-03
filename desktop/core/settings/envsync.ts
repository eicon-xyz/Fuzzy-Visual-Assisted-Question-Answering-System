/**
 * Sidecar .env 同步纯逻辑 —— HAJIMI_UI/core/env_sync.py 1:1 移植。
 * 关键语义：解析/跳注释、upsert 保序、**空设置不覆盖 Sidecar 已有 key**、
 * LLM_PROVIDER 默认 deepseek。文件 I/O 在 electron/services/settingsStore.ts。
 */

export const L5_SIDECAR_SYNC_KEYS = [
  'DEEPSEEK_API_KEY',
  'DEEPSEEK_BASE_URL',
  'DEEPSEEK_MODEL',
  'LLM_PROVIDER',
  'LLM_API_KEY',
  'LLM_BASE_URL',
  'LLM_MODEL',
  'HAJIMI_DEMO_KEY',
  'HAJIMI_HOST',
  'HAJIMI_PORT'
] as const

export interface LlmSettings {
  base_url?: string
  api_key?: string
  model?: string
}

export interface SyncInput {
  demo_key?: string
  llm?: LlmSettings
}

const KEY_LINE = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/

export function parseEnvDict(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split(/\r?\n/)) {
    const stripped = line.trim()
    if (!stripped || stripped.startsWith('#')) continue
    const m = KEY_LINE.exec(stripped)
    if (m) out[m[1]] = m[2]
  }
  return out
}

export function upsertEnvLines(lines: string[], updates: Record<string, string>): string[] {
  const seen = new Set<string>()
  const keyOf = (line: string): string | null => {
    const m = /^([A-Za-z_][A-Za-z0-9_]*)=/.exec(line.trim())
    return m ? m[1] : null
  }
  const out: string[] = []
  for (const line of lines) {
    const k = keyOf(line)
    if (k && Object.prototype.hasOwnProperty.call(updates, k)) {
      out.push(`${k}=${updates[k]}`)
      seen.add(k)
    } else {
      out.push(line)
    }
  }
  for (const [k, v] of Object.entries(updates)) {
    if (!seen.has(k)) {
      if (out.length && out[out.length - 1].trim()) out.push('')
      out.push(`${k}=${v}`)
    }
  }
  return out
}

/** _settings_to_l5_updates：用户设置 → .env 更新项（DEFAULT_DEMO_KEY 由调用方注入）。 */
export function settingsToL5Updates(
  data: SyncInput,
  defaults: { demoKey: string; host: string; port: string }
): Record<string, string> {
  const llm = data.llm ?? {}
  const updates: Record<string, string> = {
    HAJIMI_DEMO_KEY: String(data.demo_key || defaults.demoKey).trim(),
    HAJIMI_HOST: defaults.host,
    HAJIMI_PORT: defaults.port
  }
  if (llm.api_key) {
    updates.LLM_API_KEY = String(llm.api_key).trim()
    if (llm.base_url) updates.LLM_BASE_URL = String(llm.base_url).trim()
    if (llm.model) updates.LLM_MODEL = String(llm.model).trim()
  }
  return updates
}

/**
 * sync_l5_sidecar_env 的变换核心：现 .env 文本 + 用户设置 → 合并后文本。
 * existingText 为空串时按「无现值可保护」处理（对应 Python env_path 不存在分支）。
 */
export function mergeSidecarEnv(
  existingText: string,
  data: SyncInput,
  defaults: { demoKey: string; host: string; port: string }
): string {
  const updates = settingsToL5Updates(data, defaults)
  if (existingText) {
    const existing = parseEnvDict(existingText)
    for (const key of L5_SIDECAR_SYNC_KEYS) {
      if (!(key in updates) || !String(updates[key] ?? '').trim()) {
        const val = String(existing[key] ?? '').trim()
        if (val) updates[key] = val
      }
    }
  }
  if (!updates.LLM_PROVIDER) updates.LLM_PROVIDER = 'deepseek'
  const lines = existingText ? existingText.split(/\r?\n/) : []
  const merged = upsertEnvLines(lines, updates)
  return merged.join('\n').replace(/\s+$/, '') + '\n'
}
