/**
 * L5 Sidecar 根目录解析 —— 对齐 scripts/_resolve_l5_root.bat 与 core/paths.py：
 * 优先级 HAJIMI_L5_ROOT env > <repoRoot>/server_A > <repoRoot>/server_A/server_A
 * > legacy new_JIMI/HAJIMI_UI；marker = scripts/start_server.bat 存在。
 * 纯函数（exists 注入），主进程与测试共用。
 */

export interface RootCandidates {
  envOverride: string
  /** 仓根（desktop/ 的上级目录） */
  repoRoot: string
}

export function candidateL5Roots({ envOverride, repoRoot }: RootCandidates): string[] {
  const norm = (p: string) => p.replace(/[\\/]+$/, '')
  if (envOverride.trim()) return [envOverride.trim()]
  const base = norm(repoRoot)
  return [
    `${base}/server_A`,
    `${base}/server_A/server_A`,
    `${base}/new_JIMI/HAJIMI_UI`
  ]
}

export function resolveL5Root(
  candidates: RootCandidates,
  exists: (p: string) => boolean
): string | null {
  const list = candidateL5Roots(candidates)
  for (const root of list) {
    if (exists(`${root.replace(/[\\/]+$/, '')}/scripts/start_server.bat`)) return root
  }
  return null
}
