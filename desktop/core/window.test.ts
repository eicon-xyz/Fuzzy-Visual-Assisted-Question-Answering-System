import { describe, expect, it } from 'vitest'
import { clampWindowSize } from './window'

describe('clampWindowSize（PyQt resize_window 语义对齐）', () => {
  it('低于下限按 280x52 兜底', () => {
    const s = clampWindowSize(100, 10)
    expect(s.w).toBe(280)
    expect(s.h).toBe(52)
  })

  it('合法尺寸取整并保留', () => {
    const s = clampWindowSize(380.7, 620.2)
    expect(s.w).toBe(380)
    expect(s.h).toBe(620)
    expect(s.minW).toBe(280)
    expect(s.minH).toBe(52)
  })

  it('0/负数不会产出非法宽度', () => {
    const s = clampWindowSize(0, -5)
    expect(s.w).toBe(280)
    expect(s.h).toBe(52)
  })
})
