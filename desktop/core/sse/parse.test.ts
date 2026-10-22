import { describe, expect, it } from 'vitest'
import { SseLineParser, TERMINAL_EVENTS } from './parse'

describe('SseLineParser', () => {
  it('完整事件块解析为消息', () => {
    const p = new SseLineParser()
    const msgs = p.push('event: step_start\ndata: {"step_index":1}\n\n')
    expect(msgs).toEqual([{ event: 'step_start', data: { step_index: 1 } }])
  })

  it('heartbeat 被丢弃', () => {
    const p = new SseLineParser()
    expect(p.push('event: heartbeat\ndata: {"ts":1}\n\n')).toEqual([])
  })

  it('跨 chunk 半行缓冲', () => {
    const p = new SseLineParser()
    expect(p.push('event: step_do')).toEqual([])
    const msgs = p.push('ne\ndata: {"step_index":2,"evidence":"x"}\n\n')
    expect(msgs[0]?.event).toBe('step_done')
    expect(msgs[0]?.data).toEqual({ step_index: 2, evidence: 'x' })
  })

  it('坏 JSON 跳过不崩', () => {
    const p = new SseLineParser()
    expect(p.push('event: log\ndata: {not-json\n\n')).toEqual([])
    expect(p.push('event: log\ndata: {"level":"info"}\n\n')).toHaveLength(1)
  })

  it('CRLF 行尾兼容', () => {
    const p = new SseLineParser()
    const msgs = p.push('event: task_done\r\ndata: {"task_id":"t1"}\r\n\r\n')
    expect(msgs).toEqual([{ event: 'task_done', data: { task_id: 't1' } }])
  })

  it('终态集合与 Sidecar 契约一致', () => {
    expect([...TERMINAL_EVENTS].sort()).toEqual([
      'task_cancelled',
      'task_done',
      'task_failed',
    ])
  })
})
