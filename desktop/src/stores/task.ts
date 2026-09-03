/**
 * L5 任务状态机（pinia store）—— app_controller.on_l5_sse_event 分发语义移植：
 * 步骤行 executing/done/failed/blocked、终态收敛、审计文案位。
 */
import { defineStore } from 'pinia'
import type { TaskEventPayload } from '../../types/ipc'

export interface ToolEntry {
  tool: string
  success?: boolean
  summary?: string
  error?: string
  errorCode?: string | null
  hint?: string | null
  at: number
}

export interface StepRow {
  stepIndex: number
  instruction: string
  status: 'pending' | 'executing' | 'done' | 'failed' | 'blocked'
  summary: string
  evidence: string
  reason: string
  screenshot: string
  tools: ToolEntry[]
}

export interface ChatMsg {
  role: 'user' | 'system'
  tone: 'normal' | 'ok' | 'warn' | 'danger'
  text: string
}

export type TaskPhase = 'idle' | 'planning' | 'running' | 'done' | 'failed' | 'cancelled' | 'blocked'

export const useTaskStore = defineStore('task', {
  state: () => ({
    phase: 'idle' as TaskPhase,
    taskId: null as string | null,
    goal: '',
    query: '',
    normalized: '',
    steps: [] as StepRow[],
    messages: [] as ChatMsg[],
    busy: false
  }),
  actions: {
    pushSystem(text: string, tone: ChatMsg['tone'] = 'normal'): void {
      this.messages.push({ role: 'system', tone, text })
    },
    resetForSubmit(query: string): void {
      this.phase = 'planning'
      this.taskId = null
      this.goal = ''
      this.query = query
      this.normalized = ''
      this.steps = []
      this.busy = true
      this.messages.push({ role: 'user', tone: 'normal', text: query })
    },
    /** @returns true = 事件被消费（App 层不再兜底） */
    onTaskEvent(p: TaskEventPayload): void {
      if (p.taskId && this.taskId && p.taskId !== this.taskId) return
      const data = (p.data ?? {}) as Record<string, unknown>
      switch (p.event) {
        case '_submitted': {
          this.taskId = (p.taskId as string) ?? null
          this.goal = String(data.goal ?? '')
          this.normalized = String(data.normalized ?? '')
          if (this.normalized && this.normalized !== this.query.trim()) {
            this.pushSystem(`指令已按 L5 规范改写：「${this.normalized}」`, 'normal')
          }
          for (const s of (data.steps ?? []) as Array<Record<string, unknown>>) {
            this.steps.push({
              stepIndex: Number(s.step_index ?? this.steps.length + 1),
              instruction: String(s.instruction ?? ''),
              status: 'pending',
              summary: '',
              evidence: '',
              reason: '',
              screenshot: '',
              tools: []
            })
          }
          this.phase = 'running'
          this.pushSystem('L5 自动执行已启动。', 'ok')
          break
        }
        case 'step_start': {
          const idx = Number(data.step_index ?? 1)
          const row = this.ensureStep(idx, String(data.instruction ?? ''))
          row.status = 'executing'
          this.phase = 'running'
          break
        }
        case 'step_done': {
          const row = this.ensureStep(Number(data.step_index ?? 1))
          row.status = 'done'
          row.summary = String(data.action_summary ?? '')
          row.evidence = String(data.evidence ?? '')
          break
        }
        case 'step_blocked': {
          const row = this.ensureStep(Number(data.step_index ?? 1))
          row.status = 'blocked'
          // P0-0.7 契约：ask_user 终止时 engine 发 {question, reason}；旧口径 message 兜底
          row.reason = String(
            data.message ?? data.question ?? data.reason ?? '检测到高风险步骤，等待处理'
          )
          this.phase = 'blocked'
          this.pushSystem(row.reason, 'danger')
          break
        }
        case 'step_failed': {
          const row = this.ensureStep(Number(data.step_index ?? 1))
          row.status = 'failed'
          row.reason = String(
            data.reason ?? data.action_summary ?? data.error ?? '步骤失败'
          )
          break
        }
        case 'tool_called': {
          const cur = this.currentStep()
          cur?.tools.push({
            tool: String(data.tool ?? ''),
            at: Date.now()
          })
          break
        }
        case 'tool_result': {
          const cur = this.currentStep()
          if (cur) {
            const t: ToolEntry = {
              tool: String(data.tool ?? ''),
              success: data.success === true,
              summary: data.action_summary ? String(data.action_summary) : undefined,
              error: data.error ? String(data.error) : undefined,
              errorCode: (data.error_code as string | null) ?? null,
              hint: (data.hint as string | null) ?? null,
              at: Date.now()
            }
            const last = [...cur.tools].reverse().find((x) => x.tool === t.tool && x.success === undefined)
            if (last) Object.assign(last, t)
            else cur.tools.push(t)
          }
          break
        }
        case 'screenshot_updated': {
          const cur = this.currentStep()
          const img = String(data.annotated_image ?? '')
          if (cur && img) cur.screenshot = img
          break
        }
        case 'log': {
          const msg = String(data.message ?? '')
          if (msg) this.pushSystem(msg, data.level === 'warn' ? 'warn' : 'normal')
          break
        }
        case '_stream_error': {
          this.pushSystem(String(data.message ?? 'L5 连接中断'), 'danger')
          this.phase = 'failed'
          this.busy = false
          break
        }
        case 'task_done': {
          this.phase = 'done'
          this.busy = false
          for (const s of this.steps) if (s.status === 'executing' || s.status === 'pending') s.status = 'done'
          this.pushSystem('L5 执行完成。', 'ok')
          break
        }
        case 'task_failed': {
          this.phase = 'failed'
          this.busy = false
          this.pushSystem(
            `L5 执行失败：${String(data.reason ?? data.message ?? '')}`,
            'danger'
          )
          break
        }
        case 'task_cancelled': {
          this.phase = 'cancelled'
          this.busy = false
          this.pushSystem('L5 已取消。', 'warn')
          break
        }
        default:
          break
      }
    },
    ensureStep(stepIndex: number, instruction = ''): StepRow {
      let row = this.steps.find((s) => s.stepIndex === stepIndex)
      if (!row) {
        row = {
          stepIndex,
          instruction,
          status: 'executing',
          summary: '',
          evidence: '',
          reason: '',
          screenshot: '',
          tools: []
        }
        this.steps.push(row)
        this.steps.sort((a, b) => a.stepIndex - b.stepIndex)
      } else if (instruction && !row.instruction) {
        row.instruction = instruction
      }
      return row
    },
    currentStep(): StepRow | null {
      return (
        [...this.steps].reverse().find((s) => s.status === 'executing' || s.status === 'blocked') ??
        this.steps[this.steps.length - 1] ??
        null
      )
    }
  }
})
