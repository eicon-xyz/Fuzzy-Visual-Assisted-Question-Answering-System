/**
 * L5 /execute 提交前 query 归一化 —— HAJIMI_UI/core/l5_query_normalize.py 的 1:1 TS 移植。
 *
 * 目的与 Python 版一致：把「自动点击/帮我执行…」等物理操作句式改写为
 * 不触发 Sidecar physical_operation 红线的表达；privacy / realtime_dynamic
 * 类红线不改写（返回原文，交给第二层拦截）。
 *
 * 判定函数通过 RedlineChecker 注入（evaluate 端点 / 降级），本文件为纯逻辑，
 * parity 测试用 Python 生成的 golden 语料逐条锁定（见 fixtures/*.json）。
 */
import type { RedlineChecker, RedlineVerdict } from './types'

const PREFIX_RE = /^(请)?(帮我|替我|代我)\s*/

/** 顺序与 _REPLACEMENTS 严格一致（多对一替换不可乱序）。 */
const REPLACEMENTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/自动点击/g, '点击'],
  [/自动操作/g, '操作'],
  [/自动执行/g, '执行'],
  [/自动下载/g, '下载'],
  [/自动打开/g, '打开'],
  [/自动/g, ''],
  [/脚本/g, '步骤'],
  [/外挂|辅助代刷|刷量/g, '工具'],
  [/(全|自)动/g, ''],
  [/批量|循环|不停|一直|持续|定时|重复/g, ''],
  [/每\s*[0-9零一二三四五六七八九十]+\s*(秒|分|小时|天)\s*/g, ''],
  [/破解/g, ''],
]

/** _STRIP_TOKENS，顺序保留（去重兜底轮）。 */
const STRIP_TOKENS: readonly string[] = [
  '请帮我',
  '帮我',
  '替我',
  '代我',
  '自动',
  '脚本',
  '外挂',
  '辅助',
  '破解',
  '循环',
  '批量',
  '定时',
  '重复',
  '持续',
  '不停',
  '一直',
  '刷量',
]

function collapseWs(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

const PHYSICAL = 'physical_operation'

async function check(checker: RedlineChecker, query: string): Promise<RedlineVerdict> {
  try {
    return await checker(query)
  } catch {
    return { triggered: false, category: '' }
  }
}

/**
 * 改写用户 query 使其不触发 Sidecar physical_operation 红线。
 * 隐私/实时动态类红线原样返回（由第二层拦截）。
 */
export async function normalizeL5ExecuteQuery(
  query: string,
  checker: RedlineChecker
): Promise<string> {
  const original = (query ?? '').trim()
  if (!original) return original

  const initial = await check(checker, original)
  if (initial.triggered && initial.category !== PHYSICAL) return original

  let q = original.replace(PREFIX_RE, '')
  for (const [pattern, repl] of REPLACEMENTS) q = q.replace(pattern, repl)
  q = collapseWs(q)

  if ((await check(checker, q)).triggered) {
    for (const token of STRIP_TOKENS) q = q.split(token).join('')
    q = collapseWs(q)
  }

  if ((await check(checker, q)).triggered && !q.startsWith('怎么')) {
    q = `怎么${q}`
  }

  if ((await check(checker, q)).triggered) {
    const core = (q.startsWith('怎么') ? q.slice(2) : q).trim()
    q = core ? `完成操作：${core}` : q
  }

  if ((await check(checker, q)).triggered) {
    const core = q.replace(/^(怎么|完成操作：)\s*/, '').trim()
    q = core ? `打开并完成：${core}` : original
  }

  return q || original
}
