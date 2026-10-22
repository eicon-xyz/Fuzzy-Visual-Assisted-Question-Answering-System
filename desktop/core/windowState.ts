/**
 * 窗口状态持久化纯逻辑：恢复前校验，防止多屏变化后窗口漂到不可见区域。
 */
import { clampWindowSize } from './window'

export interface WindowState {
  x?: number
  y?: number
  w: number
  h: number
  compact?: boolean
}

export interface ScreenBox {
  width: number
  height: number
}

/**
 * 校验并夹紧：尺寸走 clampWindowSize 下限；
 * 位置若完全越出屏幕（可见像素 < 40）则丢弃 x/y（居中重开）。
 */
export function sanitizeWindowState(s: unknown, screen: ScreenBox): WindowState {
  const raw = (s ?? {}) as Record<string, unknown>
  const min = { minW: 280, minH: 52 }
  const size = clampWindowSize(Number(raw.w) || 380, Number(raw.h) || 620, min)
  const out: WindowState = { w: size.w, h: size.h, compact: Boolean(raw.compact) }
  const x = Number(raw.x)
  const y = Number(raw.y)
  if (Number.isFinite(x) && Number.isFinite(y)) {
    const visible =
      (x as number) > 40 - size.w &&
      (x as number) < screen.width - 40 &&
      (y as number) >= 0 &&
      (y as number) < screen.height - 40
    if (visible) {
      out.x = Math.round(x)
      out.y = Math.round(y)
    }
  }
  if (out.compact) out.h = Math.max(52, Math.min(out.h, 64))
  return out
}
