/**
 * Sidecar HTTP 客户端（主进程专用；X-Demo-Key 不出主进程）。
 * 错误文案与 HAJIMI_UI/core/api_client.py 对齐（contract.ts）。
 */
import type { DesktopConfig } from '../../core/config'
import type { RedlineVerdict } from '../../core/redline/types'
import {
  apiErrorMessage,
  buildExecuteBody,
  healthIsUsable,
  validateExecuteResponse,
  type HealthPayload
} from '../../core/client/contract'

export class SidecarError extends Error {}

export class SidecarClient {
  constructor(private cfg: DesktopConfig) {}

  private async requestJson(
    path: string,
    init: RequestInit,
    timeoutMs: number
  ): Promise<Record<string, unknown>> {
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), timeoutMs)
    try {
      const resp = await fetch(`${this.cfg.apiBaseUrl}${path}`, { ...init, signal: ctrl.signal })
      const text = await resp.text()
      if (!resp.ok) {
        if (resp.status === 401) throw new SidecarError(apiErrorMessage(401, text))
        throw new SidecarError(apiErrorMessage(resp.status, text))
      }
      return JSON.parse(text) as Record<string, unknown>
    } catch (err) {
      if (err instanceof SidecarError) throw err
      const name = (err as Error)?.name === 'AbortError' ? 'timeout' : String((err as Error)?.message || err)
      throw new SidecarError(
        `L5 Sidecar 不可达 (${name})。请先运行: ${this.cfg.l5RootOverride ? 'HAJIMI_L5_ROOT 指向的 Sidecar' : 'start_l5_sidecar.bat'}`
      )
    } finally {
      clearTimeout(timer)
    }
  }

  /** _fetch_l5_health_live：/health/live 优先，404 回退 /health；503 → degraded。 */
  async healthLive(): Promise<HealthPayload | null> {
    for (const path of ['/api/demo/health/live', '/api/demo/health']) {
      const ctrl = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), this.cfg.healthTimeoutMs)
      try {
        const resp = await fetch(`${this.cfg.apiBaseUrl}${path}`, { signal: ctrl.signal })
        if (resp.status === 404) continue
        if (resp.status !== 200 && resp.status !== 503) continue
        let data: HealthPayload = {}
        try {
          data = (await resp.json()) as HealthPayload
        } catch {
          /* body 不可解析按空 payload */
        }
        if (path.endsWith('/health') && resp.status === 503) {
          return { status: 'ok', degraded: true, ...data }
        }
        return data
      } catch {
        continue
      } finally {
        clearTimeout(timer)
      }
    }
    return null
  }

  async isHealthy(): Promise<boolean> {
    return healthIsUsable(await this.healthLive())
  }

  async execute(query: string): Promise<Record<string, unknown>> {
    const data = await this.requestJson(
      '/api/demo/execute',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Demo-Key': this.cfg.demoKey },
        body: JSON.stringify(buildExecuteBody(query))
      },
      this.cfg.executeTimeoutMs
    )
    const v = validateExecuteResponse(data)
    if (!v.ok) throw new SidecarError(v.error || 'L5 执行提交失败')
    return data
  }

  async cancel(taskId: string): Promise<void> {
    await this.requestJson(
      '/api/demo/cancel',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Demo-Key': this.cfg.demoKey },
        body: JSON.stringify({ task_id: taskId })
      },
      Math.min(this.cfg.apiTimeoutMs, 30_000)
    )
  }

  /** 审计上报（POST /api/audit/report，X-Demo-Key）；fire-and-forget，失败静默。 */
  async sendAudit(clientId: string, record: object): Promise<void> {
    try {
      await this.requestJson(
        '/api/audit/report',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Demo-Key': this.cfg.demoKey },
          body: JSON.stringify({ client_id: clientId, batch: [record] })
        },
        10_000
      )
    } catch {
      /* 审计失败不影响任务链路（PyQt 端同为尽力而为） */
    }
  }

  /**
   * 红线只读评估（第一层判定入口，POST /api/demo/redline/evaluate）。
   * 失败时抛错 —— normalize.check() 捕获后按降级语义（未触发）继续，
   * 与 PyQt 端 sidecar_modules 不可达时的 _NoRedline 行为一致。
   */
  async redlineVerdict(query: string): Promise<RedlineVerdict> {
    const data = await this.requestJson(
      '/api/demo/redline/evaluate',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Demo-Key': this.cfg.demoKey },
        body: JSON.stringify({ query })
      },
      this.cfg.apiTimeoutMs
    )
    return {
      triggered: Boolean(data.triggered),
      category: String(data.category ?? '')
    }
  }
}
