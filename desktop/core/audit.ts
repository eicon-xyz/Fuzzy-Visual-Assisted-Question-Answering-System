/**
 * 审计记录组装 —— HAJIMI_UI/core/bc_signals.AuditRecordBuilder 移植。
 * L5 任务按 route="L3" 上报（契约兼容口径与 PyQt 一致）。
 */

export interface AuditInput {
  taskId: string | null
  query: string
  intentCategory?: string
  route?: string
  totalSteps: number
  completedSteps: number
  result: 'success' | 'fail' | 'cancel' | 'rejected'
  startedAtMs: number | null
  fingerprintMismatches?: number
  redlineTriggered?: boolean
  nowSec?: number
}

export interface AuditRecord {
  task_id: string
  query: string
  intent_category: string
  complexity_score: number
  route: string
  total_steps: number
  completed_steps: number
  result: string
  duration_ms: number
  fingerprint_mismatches: number
  redline_triggered: boolean
  timestamp: string
}

export function buildAuditRecord(input: AuditInput): AuditRecord {
  const nowSec = input.nowSec ?? Date.now() / 1000
  const durationMs =
    input.startedAtMs !== null ? Math.max(0, Math.floor((nowSec * 1000 - input.startedAtMs))) : 0
  const category = input.intentCategory || 'operation_guide'
  const steps = input.totalSteps
  const query = input.query || ''
  let complexity = Math.min(100, Math.max(0, steps * 10 + Math.floor(query.length / 4)))
  if (steps === 0 && query.length === 0) complexity = 0
  let route = input.route || 'L3'
  if (route !== 'L2' && route !== 'L3') {
    route = route.toUpperCase().startsWith('L3') ? 'L3' : 'L2'
  }
  return {
    task_id: input.taskId || '',
    query,
    intent_category: category,
    complexity_score: complexity,
    route,
    total_steps: steps,
    completed_steps: Math.max(0, Math.min(input.completedSteps, steps)),
    result: input.result,
    duration_ms: durationMs,
    fingerprint_mismatches: input.fingerprintMismatches ?? 0,
    redline_triggered: input.redlineTriggered ?? input.result === 'rejected',
    timestamp: new Date(nowSec * 1000).toISOString()
  }
}
