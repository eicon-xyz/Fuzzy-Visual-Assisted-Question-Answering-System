import { describe, expect, it } from 'vitest'
import { sanitizeWindowState } from './windowState'

describe('sanitizeWindowState', () => {
  it('合法状态原样保留', () => {
    const s = sanitizeWindowState({ x: 100, y: 200, w: 380, h: 620 }, { width: 1920, height: 1080 })
    expect(s).toEqual({ w: 380, h: 620, compact: false, x: 100, y: 200 })
  })

  it('越出屏幕的位置被丢弃（居中重开）', () => {
    const s = sanitizeWindowState({ x: 5000, y: 4000, w: 380, h: 620 }, { width: 1920, height: 1080 })
    expect(s.x).toBeUndefined()
    expect(s.y).toBeUndefined()
  })

  it('边缘部分可见仍保留；几乎不可见则丢弃', () => {
    const ok = sanitizeWindowState({ x: 1600, y: 300, w: 380, h: 620 }, { width: 1920, height: 1080 })
    expect(ok.x).toBe(1600) // 右缘越界 60px，仍有 320px 可见
    const gone = sanitizeWindowState({ x: 1890, y: 1070, w: 380, h: 620 }, { width: 1920, height: 1080 })
    expect(gone.x).toBeUndefined() // 可见 <40px
  })

  it('compact 模式高度夹紧到 52-64', () => {
    const s = sanitizeWindowState({ w: 380, h: 620, compact: true }, { width: 1920, height: 1080 })
    expect(s.h).toBe(64)
  })

  it('垃圾输入不崩', () => {
    const s = sanitizeWindowState(null, { width: 1920, height: 1080 })
    expect(s.w).toBe(380)
  })
})
