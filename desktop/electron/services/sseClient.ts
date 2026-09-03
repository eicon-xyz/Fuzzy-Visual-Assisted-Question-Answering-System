/**
 * SSE 消费：GET /api/demo/stream/{task_id}（无鉴权，与现行 Sidecar 契约一致）。
 * execute_worker._consume_sse 语义 1:1：heartbeat 丢、终态断流；
 * 断线（非 abort 且未终态）由 taskRunner 决定重订阅一次。
 */
import { SseLineParser, TERMINAL_EVENTS, type SseMessage } from '../../core/sse/parse'
import type { DesktopConfig } from '../../core/config'

export type StreamOutcome = 'terminal' | 'aborted' | 'error'

export async function consumeTaskStream(opts: {
  apiBaseUrl: string
  taskId: string
  cfg: DesktopConfig
  onEvent: (e: SseMessage) => void
  signal: AbortSignal
}): Promise<StreamOutcome> {
  const { apiBaseUrl, taskId, onEvent, signal } = opts
  let resp: Response
  try {
    resp = await fetch(`${apiBaseUrl}/api/demo/stream/${taskId}`, { signal })
  } catch {
    return signal.aborted ? 'aborted' : 'error'
  }
  if (!resp.ok || !resp.body) return 'error'

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  const parser = new SseLineParser()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      for (const msg of parser.push(decoder.decode(value, { stream: true }))) {
        onEvent(msg)
        if (TERMINAL_EVENTS.has(msg.event)) {
          void reader.cancel().catch(() => undefined)
          return 'terminal'
        }
      }
    }
    // 服务端正常收尾但没见到终态事件 → 视为 error（触发上层一次重订阅）
    return 'error'
  } catch {
    return signal.aborted ? 'aborted' : 'error'
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
}
