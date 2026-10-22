/**
 * 纯逻辑：窗口尺寸约束。对齐 PyQt AppController.resize_window：
 *   width = max(280, w); height = max(52, h)
 * 主进程与测试共用，禁止 import electron。
 */
export interface SizeLimits {
  minW: number
  minH: number
}

export interface WindowSize {
  w: number
  h: number
  minW: number
  minH: number
}

export function clampWindowSize(
  w: number,
  h: number,
  limits: SizeLimits = { minW: 280, minH: 52 }
): WindowSize {
  const minW = Math.max(1, Math.trunc(limits.minW))
  const minH = Math.max(1, Math.trunc(limits.minH))
  return {
    w: Math.max(minW, Math.trunc(w) || minW),
    h: Math.max(minH, Math.trunc(h) || minH),
    minW,
    minH
  }
}
