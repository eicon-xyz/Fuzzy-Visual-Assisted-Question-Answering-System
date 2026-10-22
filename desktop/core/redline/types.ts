/**
 * 红线判定接口注入位。
 * 真实实现（M1 sidecar client）：POST /api/demo/redline/evaluate；
 * Sidecar 不可达时降级 = 恒「未触发」——与 PyQt 端 _NoRedline 语义一致。
 */
export interface RedlineVerdict {
  triggered: boolean
  /** physical_operation | personal_privacy | realtime_dynamic | "" */
  category: string
}

export type RedlineChecker = (query: string) => Promise<RedlineVerdict>

/** 降级 checker：未触发（现行 PyQt 在规则源不可达时的行为）。 */
export const NO_REDLINE: RedlineVerdict = { triggered: false, category: '' }
