# server/docs — 已清空

L4 时代（旧 A 端 :8010 / OmniParser / 校园 GPU 内网联调）运行文档，已于 2026-09-03 归档到 `archive/legacy-L4/`，
又于 2026-10-17 **移出主线**，存于 git 分支 `docs/archive` 的
`server_A/server/docs/archive/legacy-L4/`（**禁止照做，仅可追溯**）。

取回查阅：

```bash
git checkout docs/archive -- server_A/server/docs/archive/legacy-L4
```

为什么要移出去：这些文件描述的是已经删除的架构（:8010 / deployment_mode / a_end_url / OmniParser）。
留在主线里，agent 打开任何一份都会把旧实现学回去——比"缺文档"贵得多。

现行 Sidecar 开发指南：仓库根 [`AGENTS.md`](../../../AGENTS.md) + [`server_A/CLAUDE.md`](../../CLAUDE.md)。
