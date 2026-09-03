/**
 * 任务编排（主进程）：知情确认 → 红线第一层归一化 → /execute → SSE → IPC 广播。
 * 对应 PyQt：app_controller.submit_query + execute_worker.run + on_l5_sse_event 分发。
 */
import { BrowserWindow } from 'electron'
import { normalizeL5ExecuteQuery } from '../../core/redline/normalize'
import type { SidecarClient } from './sidecarClient'
import { consumeTaskStream } from './sseClient'
import type { DesktopConfig } from '../../core/config'
import type { SseMessage } from '../../core/sse/parse'

export interface SubmitResult {
  ok: boolean
  taskId?: string
  normalized?: string
  /** 用户取消知情确认 */
  consentDeclined?: boolean
  error?: string
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export class TaskRunner {
  private current: { taskId: string; ctrl: AbortController } | null = null

  constructor(
    private client: SidecarClient,
    private cfg: DesktopConfig,
    private getWin: () => BrowserWindow | null,
    private consentAccepted: () => boolean,
    /** 用户同意本次执行；dontShowAgain=true 才持久化（对齐 PyQt「不再提示」勾选） */
    private markConsent: (dontShowAgain: boolean) => void
  ) {}

  private broadcast(payload: { taskId?: string; event: string; data: unknown }): void {
    this.getWin()?.webContents.send('task:event', payload)
  }

  async submit(rawQuery: string, acceptConsent: boolean, dontShowAgain = true): Promise<SubmitResult> {
    if (this.current) return { ok: false, error: '已有 L5 任务在执行中' }
    if (!this.consentAccepted()) {
      if (!acceptConsent) return { ok: false, consentDeclined: true }
      this.markConsent(dontShowAgain)
    }

    // Sidecar 不健康时先尝试拉起（等价 _ensure_l5_ready + auto-launch；
    // sidecarManager 注入点：main 在 submit 前调用 ensureRunning）
    // 第一层红线：归一化（checker = evaluate 端点，失败降级同 PyQt）
    let normalized: string
    try {
      normalized = await normalizeL5ExecuteQuery(rawQuery, (q) =>
        this.client.redlineVerdict(q)
      )
    } catch (err) {
      return { ok: false, error: `红线第一层异常: ${(err as Error).message}` }
    }

    try {
      const data = await this.client.execute(normalized)
      const taskId = String(data.task_id)
      this.current = { taskId, ctrl: new AbortController() }
      this.broadcast({
        taskId,
        event: '_submitted',
        data: {
          query: rawQuery,
          normalized,
          goal: data.goal ?? '',
          steps: data.steps ?? [],
          plan: data.plan ?? null
        }
      })
      void this.runStream(taskId)
      return { ok: true, taskId, normalized }
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
  }

  private async runStream(taskId: string): Promise<void> {
    const cur = this.current
    if (!cur) return
    let attempts = 0
    for (;;) {
      const outcome = await consumeTaskStream({
        apiBaseUrl: this.cfg.apiBaseUrl,
        taskId,
        cfg: this.cfg,
        signal: cur.ctrl.signal,
        onEvent: (e: SseMessage) => this.broadcast({ taskId, event: e.event, data: e.data })
      })
      if (outcome === 'terminal' || outcome === 'aborted') break
      if (attempts >= 1) {
        this.broadcast({
          taskId,
          event: '_stream_error',
          data: { message: 'L5 连接中断：SSE 重订阅失败' }
        })
        break
      }
      attempts += 1
      await sleep(300)
    }
    if (this.current?.taskId === taskId) this.current = null
  }

  async cancel(): Promise<{ ok: boolean; error?: string }> {
    const cur = this.current
    if (!cur) return { ok: false, error: '当前没有执行中的 L5 任务' }
    try {
      await this.client.cancel(cur.taskId)
    } catch (err) {
      return { ok: false, error: (err as Error).message }
    }
    cur.ctrl.abort()
    return { ok: true }
  }

  abortLocal(): void {
    this.current?.ctrl.abort()
    this.current = null
  }
}
