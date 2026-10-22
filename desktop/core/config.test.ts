import { describe, expect, it } from 'vitest'
import { candidateL5Roots, resolveL5Root } from './l5root'
import { configFromEnv } from './config'

describe('resolveL5Root（_resolve_l5_root.bat 语义对齐）', () => {
  const tree = (files: string[]) => (p: string) => files.includes(p)

  it('flat server_A 优先命中', () => {
    const root = resolveL5Root(
      { envOverride: '', repoRoot: '/repo' },
      tree(['/repo/server_A/scripts/start_server.bat'])
    )
    expect(root).toBe('/repo/server_A')
  })

  it('nested 与 legacy 依序回退', () => {
    const r1 = resolveL5Root(
      { envOverride: '', repoRoot: '/repo' },
      tree(['/repo/server_A/server_A/scripts/start_server.bat'])
    )
    expect(r1).toBe('/repo/server_A/server_A')
    const r2 = resolveL5Root(
      { envOverride: '', repoRoot: '/repo' },
      tree(['/repo/new_JIMI/HAJIMI_UI/scripts/start_server.bat'])
    )
    expect(r2).toBe('/repo/new_JIMI/HAJIMI_UI')
  })

  it('env 覆盖直取（不做 marker 检查，与 bat 一致）', () => {
    const roots = candidateL5Roots({ envOverride: 'D:/custom/server_A', repoRoot: '/repo' })
    expect(roots).toEqual(['D:/custom/server_A'])
  })

  it('找不到返回 null', () => {
    expect(resolveL5Root({ envOverride: '', repoRoot: '/repo' }, () => false)).toBeNull()
  })
})

describe('configFromEnv（PyQt config.py 口径）', () => {
  it('默认值', () => {
    const c = configFromEnv({})
    expect(c.apiBaseUrl).toBe('http://127.0.0.1:8011')
    expect(c.demoKey).toBe('hajimi-demo-2026')
    expect(c.executeTimeoutMs).toBe(360_000)
    expect(c.stopServicesOnExit).toBe(true)
    expect(c.skipLogin).toBe(false)
  })

  it('L5_API_URL 覆盖 host/port', () => {
    const c = configFromEnv({
      L5_API_URL: 'http://127.0.0.1:9999/',
      L5_API_HOST: '10.0.0.1',
      L5_API_PORT: '1234'
    })
    expect(c.apiBaseUrl).toBe('http://127.0.0.1:9999')
  })

  it('host/port 组合与布尔 env', () => {
    const c = configFromEnv({
      L5_API_HOST: '10.1.2.3',
      L5_API_PORT: '8022',
      HAJIMI_SKIP_LOGIN: '1',
      HAJIMI_STOP_SERVICES_ON_EXIT: 'false'
    })
    expect(c.apiBaseUrl).toBe('http://10.1.2.3:8022')
    expect(c.skipLogin).toBe(true)
    expect(c.stopServicesOnExit).toBe(false)
  })
})
