/**
 * 登录会话（主进程）：auth_session.py 移植。
 * 会话文件与 PyQt 同位置同格式：%LOCALAPPDATA%\HAJIMI\auth_session.json（双端互认）。
 */
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import type { DesktopConfig } from '../../core/config'
import {
  createLocalDemoSession,
  extractLoginError,
  isDemoCredentials,
  isSessionValid,
  normalizeLoginResponse,
  type Session
} from '../../core/settings/auth'

function sessionPath(): string {
  const base = process.env.LOCALAPPDATA || homedir()
  const dir = join(base, 'HAJIMI')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  return join(dir, 'auth_session.json')
}

export class AuthSession {
  constructor(private cfg: DesktopConfig) {}

  load(): Session | null {
    try {
      const data = JSON.parse(readFileSync(sessionPath(), 'utf-8')) as Session
      return data && typeof data === 'object' ? data : null
    } catch {
      return null
    }
  }

  private save(session: Session): Session {
    writeFileSync(sessionPath(), JSON.stringify(session, null, 2), 'utf-8')
    return session
  }

  isValid(): boolean {
    return isSessionValid(this.load())
  }

  username(): string {
    const s = this.load()
    return String(s?.user?.username || s?.username || 'admin')
  }

  /** login(username, password)：POST /api/auth/login；离线 + demo 凭据 → 本地会话。 */
  async login(username: string, password: string): Promise<Session> {
    let raw: Record<string, unknown>
    try {
      const resp = await fetch(`${this.cfg.apiBaseUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(15_000)
      })
      const text = await resp.text()
      if (!resp.ok) throw new Error(extractLoginError(text, resp.status))
      raw = JSON.parse(text) as Record<string, unknown>
    } catch (err) {
      const msg = (err as Error).message || String(err)
      if (/fetch failed|timeout|abort|ECONN/i.test(msg)) {
        if (isDemoCredentials(username, password)) {
          return this.save(createLocalDemoSession(username.trim()))
        }
        throw new Error(
          `无法连接 L5 Sidecar (${this.cfg.apiBaseUrl})。请先启动服务或设置 HAJIMI_SKIP_LOGIN=1`
        )
      }
      throw new Error(msg)
    }
    const normalized = normalizeLoginResponse(raw, username)
    return this.save({
      access_token: normalized.access_token,
      refresh_token: normalized.refresh_token ?? null,
      user: (normalized.user as Session['user']) ?? { username, role: 'admin' },
      username,
      expires_at: Date.now() / 1000 + (normalized.expires_in || 7200)
    })
  }

  logout(): void {
    try {
      if (existsSync(sessionPath())) unlinkSync(sessionPath())
    } catch {
      /* ignore */
    }
  }
}
