import { describe, expect, it } from 'vitest'
import { buildAuditRecord } from './audit'

describe('AuditRecordBuilder 移植', () => {
  it('L5 终态记录：route 固定 L3、复杂度按步数/长度、completed 截断', () => {
    const r = buildAuditRecord({
      taskId: 't1',
      query: '打开记事本并输入文字',
      totalSteps: 3,
      completedSteps: 5,
      result: 'success',
      startedAtMs: 1000_000,
      nowSec: 1010
    })
    expect(r.route).toBe('L3')
    expect(r.intent_category).toBe('operation_guide')
    expect(r.complexity_score).toBe(3 * 10 + Math.floor('打开记事本并输入文字'.length / 4))
    expect(r.completed_steps).toBe(3) // clamp 到 total
    expect(r.duration_ms).toBe(10_000)
    expect(r.result).toBe('success')
    expect(r.redline_triggered).toBe(false)
    expect(Date.parse(r.timestamp)).toBeCloseTo(1010 * 1000, -2)
  })

  it('rejected → redline_triggered=true；route 归一化', () => {
    expect(buildAuditRecord({ taskId: null, query: 'x', totalSteps: 0, completedSteps: 0, result: 'rejected', startedAtMs: null }).redline_triggered).toBe(true)
    expect(buildAuditRecord({ taskId: '', query: '', totalSteps: 1, completedSteps: 1, result: 'fail', startedAtMs: null, route: 'l5' }).route).toBe('L2')
  })
})
