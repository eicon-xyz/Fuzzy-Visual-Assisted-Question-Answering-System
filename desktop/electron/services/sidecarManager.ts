/**
 * Sidecar 生命周期管理：health 探测 → 必要时 spawn uvicorn → 轮询就绪 → 退出清理。
 * 行为对齐 core/l5_sidecar_launcher.py（不弹控制台窗口、后台守护、可关）。
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { resolveL5Root } from '../../core/l5root'
import type { DesktopConfig } from '../../core/config'
import type { SidecarClient } from './sidecarClient'

export type SidecarPhase = 'running' | 'starting' | 'spawned' | 'missing' | 'failed'

export interface SidecarState {
  phase: SidecarPhase
  detail: string
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export class SidecarManager {
  private child: ChildProcess | null = null

  constructor(
    private client: SidecarClient,
    private cfg: DesktopConfig,
    /** desktop/ 的上级 = 仓根；打包后由 main 传 app.getAppPath() 推导 */
    private repoRoot: string,
    private onState: (s: SidecarState) => void
  ) {}

  private port(): string {
    try {
      return new URL(this.cfg.apiBaseUrl).port || '8011'
    } catch {
      return '8011'
    }
  }

  private pythonCandidates(l5Root: string): string[] {
    const win = process.platform === 'win32'
    const venv = win
      ? join(l5Root, 'server', '.venv', 'Scripts', 'python.exe')
      : join(l5Root, 'server', '.venv', 'bin', 'python')
    // venv 优先；缺失时回退 PATH 上的解释器（对齐 bat 的 python 兜底）
    return [venv, ...(win ? ['python'] : ['python3', 'python'])]
  }

  /** 已就绪？ */
  async isRunning(): Promise<boolean> {
    return this.client.isHealthy()
  }

  /**
   * 确保 Sidecar 可用：探活 → 拉起 → 轮询（默认 ~40s）。
   * 对齐 ensure_l5_sidecar_running 返回 (ok, reason)。
   */
  async ensureRunning(pollTimeoutMs = 40_000): Promise<{ ok: boolean; reason: string }> {
    if (await this.client.isHealthy()) {
      this.onState({ phase: 'running', detail: 'Sidecar 已在运行' })
      return { ok: true, reason: '' }
    }
    this.onState({ phase: 'starting', detail: 'L5 Sidecar 未运行，正在拉起…' })

    const l5Root = resolveL5Root(
      { envOverride: this.cfg.l5RootOverride, repoRoot: this.repoRoot },
      existsSync
    )
    if (!l5Root) {
      const reason = `未找到 L5 Sidecar（server_A）。可设 HAJIMI_L5_ROOT 指定路径。`
      this.onState({ phase: 'missing', detail: reason })
      return { ok: false, reason }
    }

    const port = this.port()
    const candidates = this.pythonCandidates(l5Root)
    // venv 解释器存在才用绝对路径；PATH 兜底交给 spawn 解析
    const python = candidates.find((c) => existsSync(c)) ?? candidates[candidates.length - 1]
    try {
      this.child = spawn(
        python,
        ['-m', 'uvicorn', 'server.main:app', '--host', '127.0.0.1', '--port', port],
        {
          cwd: l5Root,
          env: { ...process.env, HAJIMI_PORT: port },
          stdio: 'ignore',
          detached: false,
          windowsHide: true
        }
      )
      this.child.on('exit', (code) => {
        this.child = null
        if (code !== 0 && code !== null) {
          this.onState({ phase: 'failed', detail: `Sidecar 进程退出 (code=${code})` })
        }
      })
      this.child.on('error', (err) => {
        this.child = null
        this.onState({ phase: 'failed', detail: `Sidecar 启动失败: ${err.message}` })
      })
    } catch (err) {
      const reason = `Sidecar 启动失败: ${(err as Error).message}`
      this.onState({ phase: 'failed', detail: reason })
      return { ok: false, reason }
    }

    this.onState({ phase: 'spawned', detail: '等待 Sidecar 就绪…' })
    const deadline = Date.now() + pollTimeoutMs
    while (Date.now() < deadline) {
      await sleep(1500)
      if (await this.client.isHealthy()) {
        this.onState({ phase: 'running', detail: 'Sidecar 已就绪' })
        return { ok: true, reason: '' }
      }
    }
    const reason = `L5 Sidecar 启动超时（${Math.round(pollTimeoutMs / 1000)}s）。可查看 ${join(l5Root, 'server')} 日志或手动运行 start_l5_sidecar.bat`
    this.onState({ phase: 'failed', detail: reason })
    return { ok: false, reason }
  }

  /** 只清理自己拉起的进程（外部启动的 Sidecar 不归本端管）。 */
  shutdown(): void {
    if (this.child) {
      try {
        this.child.kill()
      } catch {
        /* ignore */
      }
      this.child = null
    }
  }
}
