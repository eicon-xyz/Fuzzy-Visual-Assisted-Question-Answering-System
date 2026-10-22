/**
 * L5 任务状态机（app_controller.on_l5_sse_event 语义移植）单测。
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTaskStore } from '../src/stores/task'

beforeEach(() => setActivePinia(createPinia()))

describe('task store 事件状态机', () => {
  it('_submitted → running，规划步骤入列', () => {
    const s = useTaskStore()
    s.resetForSubmit('帮我打开记事本')
    s.onTaskEvent({
      taskId: 't1',
      event: '_submitted',
      data: {
        goal: '打开记事本',
        normalized: '打开记事本',
        steps: [{ step_index: 1, instruction: '启动记事本' }]
      }
    })
    expect(s.phase).toBe('running')
    expect(s.steps[0].instruction).toBe('启动记事本')
    expect(s.taskId).toBe('t1')
  })

  it('step_done 收敛 summary/evidence；task_done 把执行中步骤置 done', () => {
    const s = useTaskStore()
    s.onTaskEvent({ taskId: 't', event: 'step_start', data: { step_index: 1, instruction: 'a' } })
    s.onTaskEvent({
      taskId: 't',
      event: 'step_done',
      data: { step_index: 1, action_summary: '单击 元素', evidence: 'click→确定 state_changed=True' }
    })
    expect(s.steps[0].status).toBe('done')
    expect(s.steps[0].evidence).toContain('state_changed')
    s.onTaskEvent({ taskId: 't', event: 'step_start', data: { step_index: 2, instruction: 'b' } })
    s.onTaskEvent({ taskId: 't', event: 'task_done', data: {} })
    expect(s.phase).toBe('done')
    expect(s.steps[1].status).toBe('done') // 终态兜底收敛
    expect(s.busy).toBe(false)
  })

  it('step_blocked 挂起并提示；tool_result 回填 tool_called；异 taskId 忽略', () => {
    const s = useTaskStore()
    s.onTaskEvent({ taskId: 'mine', event: '_submitted', data: { steps: [] } })
    s.onTaskEvent({ taskId: 'mine', event: 'step_start', data: { step_index: 1, instruction: 'x' } })
    s.onTaskEvent({ taskId: 'other', event: 'step_done', data: { step_index: 1 } })
    expect(s.steps[0].status).toBe('executing') // 串台事件被丢弃

    s.onTaskEvent({ taskId: 'mine', event: 'tool_called', data: { tool: 'click', args: {} } })
    s.onTaskEvent({
      taskId: 'mine',
      event: 'tool_result',
      data: { tool: 'click', success: false, error: 'not_actionable', error_code: 'not_actionable' }
    })
    expect(s.steps[0].tools).toHaveLength(1)
    expect(s.steps[0].tools[0].errorCode).toBe('not_actionable')

    s.onTaskEvent({ taskId: 'mine', event: 'step_blocked', data: { step_index: 1, question: '需要登录' } })
    expect(s.phase).toBe('blocked')
  })

  it('task_failed / _stream_error 进失败态并输出消息', () => {
    const s = useTaskStore()
    s.onTaskEvent({ taskId: 'f', event: 'task_failed', data: { reason: 'step 2 failed' } })
    expect(s.phase).toBe('failed')
    expect(s.messages.some((m) => m.text.includes('step 2 failed'))).toBe(true)
    s.busy = true
    s.onTaskEvent({ taskId: 'f', event: '_stream_error', data: { message: 'SSE 重订阅失败' } })
    expect(s.busy).toBe(false)
  })
})
