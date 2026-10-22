/**
 * SSE 解析纯逻辑（无 electron/网络依赖，vitest 直测）。
 * 事件语义对齐 HAJIMI_UI/core/execute_worker.py：
 *  - event:/data: 行协议；heartbeat 丢弃；
 *  - task_done / task_failed / task_cancelled 为终态（上层断流）。
 */

export interface SseMessage {
  event: string
  data: unknown
}

export const TERMINAL_EVENTS: ReadonlySet<string> = new Set([
  'task_done',
  'task_failed',
  'task_cancelled',
])

/** 增量行解析器：push(chunk) → 完整消息数组（跨 chunk 半行缓冲）。 */
export class SseLineParser {
  private _buf = ''
  private _event = ''

  push(chunk: string): SseMessage[] {
    this._buf += chunk
    const out: SseMessage[] = []
    for (;;) {
      const nl = this._buf.indexOf('\n')
      if (nl < 0) break
      const line = this._buf.slice(0, nl).replace(/\r$/, '')
      this._buf = this._buf.slice(nl + 1)
      const msg = this._consumeLine(line)
      if (msg) out.push(msg)
    }
    return out
  }

  private _consumeLine(line: string): SseMessage | null {
    if (line.startsWith('event:')) {
      this._event = line.slice(6).trim()
      return null
    }
    if (line.startsWith('data:') && this._event) {
      const payload = line.slice(5).trim()
      if (!payload) return null
      let data: unknown
      try {
        data = JSON.parse(payload)
      } catch {
        return null // 与 execute_worker 一致：坏 JSON 跳过
      }
      const event = this._event
      this._event = ''
      if (event === 'heartbeat') return null
      return { event, data }
    }
    return null
  }
}
