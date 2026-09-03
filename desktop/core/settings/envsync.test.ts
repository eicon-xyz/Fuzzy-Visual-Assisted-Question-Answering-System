import { describe, expect, it } from 'vitest'
import { mergeSidecarEnv, parseEnvDict, settingsToL5Updates, upsertEnvLines } from './envsync'

const DEF = { demoKey: 'hajimi-demo-2026', host: '127.0.0.1', port: '8011' }

describe('parseEnvDict / upsertEnvLines', () => {
  it('解析 KEY=VALUE 跳注释/空行', () => {
    const d = parseEnvDict('# c\n\nA=1\nB=x=y\n")  bad')
    expect(d.A).toBe('1')
    expect(d.B).toBe('x=y')
  })
  it('upsert 原位替换 + 新键追加', () => {
    const out = upsertEnvLines(['A=1', 'keep=2'], { A: '9', C: '3' })
    expect(out).toContain('A=9')
    expect(out).toContain('keep=2')
    expect(out.join('\n')).toMatch(/A=9\nkeep=2\n\nC=3$/)
  })
})

describe('settingsToL5Updates', () => {
  it('无 api_key 时不带 LLM_*（不误清）', () => {
    const u = settingsToL5Updates({ llm: { model: 'deepseek-chat' } }, DEF)
    expect(u.LLM_API_KEY).toBeUndefined()
    expect(u.LLM_MODEL).toBeUndefined()
    expect(u.HAJIMI_DEMO_KEY).toBe('hajimi-demo-2026')
  })
  it('demo_key 未提供 → 默认值；纯空白 trim 后为空（与 Python 一致，由 merge 空值保护兜底）', () => {
    expect(settingsToL5Updates({}, DEF).HAJIMI_DEMO_KEY).toBe('hajimi-demo-2026')
    expect(settingsToL5Updates({ demo_key: '  ' }, DEF).HAJIMI_DEMO_KEY).toBe('')
  })
})

describe('mergeSidecarEnv（env_sync.py 全语义）', () => {
  it('demo_key 空白时保留 .env 现值（空值不覆盖）', () => {
    const existing = 'HAJIMI_DEMO_KEY=k-existing\n'
    const merged = mergeSidecarEnv(existing, { demo_key: '  ' }, DEF)
    expect(parseEnvDict(merged).HAJIMI_DEMO_KEY).toBe('k-existing')
  })
  it('空设置不覆盖 Sidecar 已有 key', () => {
    const existing = 'DEEPSEEK_API_KEY=sk-secret\nLLM_API_KEY=sk-llm\nLLM_MODEL=deepseek-chat\n'
    const merged = mergeSidecarEnv(existing, { llm: {} }, DEF)
    const d = parseEnvDict(merged)
    expect(d.LLM_API_KEY).toBe('sk-llm') // 用户没填 → 保留现值
    expect(d.LLM_MODEL).toBe('deepseek-chat')
    expect(d.LLM_PROVIDER).toBe('deepseek')
  })

  it('用户填了新 key 则覆盖', () => {
    const existing = 'LLM_API_KEY=sk-old\n'
    const merged = mergeSidecarEnv(
      existing,
      { llm: { api_key: 'sk-new', base_url: 'https://api.deepseek.com', model: 'deepseek-chat' } },
      DEF
    )
    const d = parseEnvDict(merged)
    expect(d.LLM_API_KEY).toBe('sk-new')
    expect(d.LLM_BASE_URL).toBe('https://api.deepseek.com')
    expect(d.HAJIMI_PORT).toBe('8011')
  })

  it('保留原文件其余行与非同步键、注释', () => {
    const existing = '# comment line\nCUSTOM=1\nLLM_API_KEY=sk-old\n'
    const merged = mergeSidecarEnv(existing, { llm: { api_key: 'sk-x' } }, DEF)
    expect(merged).toContain('# comment line')
    expect(merged).toContain('CUSTOM=1')
    expect(merged).toContain('LLM_API_KEY=sk-x')
  })

  it('无 .env 时新建含默认骨架', () => {
    const merged = mergeSidecarEnv('', { llm: { api_key: 'k', model: 'm' } }, DEF)
    const d = parseEnvDict(merged)
    expect(d.LLM_API_KEY).toBe('k')
    expect(d.LLM_PROVIDER).toBe('deepseek')
    expect(d.HAJIMI_HOST).toBe('127.0.0.1')
  })
})
