/**
 * normalize.ts parity 测试 —— golden 语料由 desktop/scripts/gen_normalize_fixtures.py
 * 用现行 Python 实现（HAJIMI_UI/core/l5_query_normalize + server_A redline_service）生成。
 * checker 用 trace 构造：TS 侧中间形态若与 Python 不一致 → trace 缺失 → 输出偏离被断言捕获。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { normalizeL5ExecuteQuery } from '../core/redline/normalize'
import type { RedlineChecker } from '../core/redline/types'

interface Case {
  input: string
  output: string
  trace: Record<string, { triggered: boolean; category: string }>
}

const golden = JSON.parse(
  readFileSync(join(__dirname, 'fixtures/normalize_golden.json'), 'utf-8')
) as { cases: Case[] }

function checkerFrom(case_: Case): RedlineChecker {
  return async (q: string) => {
    const v = case_.trace[q]
    if (!v) {
      // 与 Python 实现分叉的信号：按降级语义返回未触发，最终输出断言会暴露偏离
      return { triggered: false, category: '' }
    }
    return { triggered: v.triggered, category: v.category }
  }
}

describe('normalizeL5ExecuteQuery ↔ Python 实现 parity（golden set）', () => {
  for (const c of golden.cases) {
    it(`"${c.input.trim() || '(空白)'}" → "${c.output || '(空)'}"`, async () => {
      const out = await normalizeL5ExecuteQuery(c.input, checkerFrom(c))
      expect(out).toBe(c.output)
    })
  }
})

describe('normalizeL5ExecuteQuery 独立行为', () => {
  it('checker 抛异常时按降级语义（未触发）只走字面改写', async () => {
    const boom: RedlineChecker = async () => {
      throw new Error('evaluate endpoint unreachable')
    }
    expect(await normalizeL5ExecuteQuery('帮我打开记事本', boom)).toBe('打开记事本')
  })

  it('空串与纯空白直接返回', async () => {
    const never: RedlineChecker = async () => {
      throw new Error('should not be called')
    }
    expect(await normalizeL5ExecuteQuery('', never)).toBe('')
    expect(await normalizeL5ExecuteQuery('   ', never)).toBe('')
  })
})
