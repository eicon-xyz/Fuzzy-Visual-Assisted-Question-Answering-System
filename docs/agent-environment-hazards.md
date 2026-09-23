# Agent 执行环境风险：工作区批量文件静默丢失

> 适用范围：在 Windows 端对 `hajimi-eval` 工作区执行 git 操作的任何 agent（Codex / WorkBuddy / 手工终端）。
> 本文自包含，不依赖其他文档即可理解与处置。

## 1. 事故概述

**时间**：2026-09-23 15:14（Asia/Shanghai）
**触发命令**：`git reset --hard origin/master`（`hajimi-eval` 从 `1459a290` 快进到 `14cc5b19`）
**现象**：`server_A/` 下 304 个受跟踪文件中 291 个从磁盘消失，`git status` 显示为 291 条 ` D`；工作区仅剩 2 个 `.py` 文件
**结果**：`git checkout-index -a -f` 全额恢复，四条验收通过，Sidecar 冒烟通过

关键定性：**这不是 git 的行为，也不是人为删除或杀毒软件，而是执行层（agent 沙箱的文件系统代理）在落地 git 的写盘请求时发生的实现缺陷。**

## 2. 机理

代理的写盘方式为「**先删除，再写入**」：

| 步骤 | 代理的行为 | 后果 |
|---|---|---|
| 1 | 把目标整棵子树删除（走 Windows 回收站 API，故进入 `$RECYCLE.BIN`） | 未跟踪文件（`__pycache__`/`.pyc`）一并被带走——git 绝不会碰未跟踪文件，这是代理行为的最直接证据 |
| 2 | 只把本次有差异的文件写回（本例 30～41 个） | 其余未变更文件不会被写回，留在回收站 |
| 3 | 索引仍认为这些文件存在且内容匹配（stat 缓存未失效） | `git status` 此前显示"干净"，问题被隐藏到下次操作才暴露 |

**风险面不止于 `reset --hard`**：任何会批量重写工作区的操作都走同一条路径——`git checkout`、`git switch`、`git stash`、`git restore`、大范围 `git checkout -- <path>`。

**旁证**：`.git\worktrees\hajimi-eval\index.lock`、`AUTO_MERGE.lock`、`packed-refs.lock` 在 15:16 / 15:19×4 / 15:22 反复进入回收站，说明**每一次文件写入都经过这条删除路径**；写单个文件时无害，整目录重写时就会静默吞掉未变更文件。

## 3. 证据链

| # | 证据 | 结论 |
|---|---|---|
| 1 | 回收站 `$I*` 元数据解码：338 个条目指向 `hajimi-eval`，删除时间戳全部 = **2026-09-23 15:14** | 删除是**一次性**发生的，时刻与 `reset --hard` 完全重合（reflog：15:14:03 checkout / 15:14:29 reset） |
| 2 | 回收站时间分布中 **09-16 ～ 09-22 无任何条目**；09-15 只有 B1 校准期的零星条目 | 排除"09-15 之后被人手工删除/ `git clean` 过"的假设 |
| 3 | `git diff --name-status 1459a290 14cc5b19 -- server_A/` 仅 **22 条路径**（9D / 3M / 10R），全仓 31 文件 | reset 本不该触碰 291 个文件 |
| 4 | 被删的 `defaults.py` / `run_eval.py` / `providers.py` / `fonts.py` / `test_perception.py` 在 `14cc5b19` 中均存在（`cat-file -e` 通过） | 这些文件属于"不应被删"的范畴 |
| 5 | 回收站中存在未跟踪路径 `__pycache__` / `*.pyc` / `server_A\data\*` | 非 git 行为（git 不动未跟踪文件，且 git 的 unlink 不会进回收站） |
| 6 | Windows Defender：`Get-MpThreatDetection` 为空；`wevtutil` 唯一 1116 事件是 `SakuraFrpLauncher.exe`（`Trojan:Win32/Kepavll!rfn`），0 条 1117 | **排除杀毒误报** |
| 7 | `D:\` 为普通本地盘（含 `$RECYCLE.BIN`、`System Volume Information`），无同步目录指向 `D:\HAJIMI_B` | **排除云同步** |
| 8 | PowerShell / shell 历史中无任何针对 `server_A` 或 `hajimi-eval` 的删除命令 | **排除历史清理命令** |
| 9 | 幸存文件恰好是本次差异文件（`test_calib.py`、`test_waa_pilot.py`） | 与"只写回差异文件"的模型完全吻合 |

## 4. 修复方法

`git checkout-index -a -f` 是**确定性修复**：它直接按索引写盘，不读工作区状态，因此绕开 stat 缓存问题；只补回缺失的受跟踪文件，不动未跟踪文件（`.env` 因此安全）。

```bat
cd /d D:\HAJIMI_B\hajimi-eval
git status --porcelain          :: 先确认为纯 D 条目（无 M / A / ?? 未提交改动）
git checkout-index -a -f
```

**验收四条，全过才算成功：**

```bat
git status --porcelain                 :: 必须空输出
git ls-files server_A/ | wc -l         :: 必须 304
ls server_A\server\main.py server_A\server\routes\demo.py server_A\server\services\executor\engine.py
ls server_A\eval\calib_evidence\       :: 6 份必须齐全
```

**Sidecar 冒烟（文件在 ≠ 能跑）：**

```bat
D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System\server_A\server\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8011
curl -s http://127.0.0.1:8011/api/demo/health
:: 期望 {"status":"ok","version":"2.0.0",...}
```

## 5. 纪律（强制执行）

| # | 纪律 | 理由 |
|---|---|---|
| 1 | **只需快进时用 `git merge --ff-only origin/master`，不用 `reset --hard`** | 本例中两者效果完全相同，但前者无破坏性选项 |
| 2 | **破坏性 git 操作（`reset --hard` / `clean` / 大范围 `checkout`·`switch`·`restore`）一律在 agent 沙箱外的终端执行**（系统 PowerShell / VS Code 终端） | 沙箱写盘即本文所述缺陷 |
| 3 | **每次 git 操作后例行 `git status --porcelain`**；非空且为纯 `D` 条目 = 缺陷又发作了 | 唯一能及时发现的手段 |
| 4 | **把工作区交给 agent 前先确认 `git status` 干净且文件齐全** | 否则 agent 会在残缺工作区上继续工作 |

## 6. 已确认的数据损失（git 补不回来）

计算方法：`回收站 15:14 批次的原始路径 − git 索引路径 = 丢失的未跟踪文件`。
结果：112 条未跟踪条目，其中 56 条为 `__pycache__` / `.pyc`（可重建）。真正有价值的损失如下：

| 路径 | 性质 | 可否重建 | 现状 |
|---|---|---|---|
| `server_A/data/hajimi.db`（含 `-shm` / `-wal`） | SQLite，7 张表（用户 / 事务 / 步骤日志 / 反馈 / 失败 / 红线日志 / 系统配置） | ⚠️ 本 worktree 副本不可恢复，**主仓库副本完好** | 见 6.1 |
| `server_A/data/eval/runs.jsonl` | 评测跑分原始结果（响应时间 / 准确率基线） | ❌ 全盘无副本 | **确认丢失** |
| `server_A/eval/results/*.jsonl` | 跑分原始结果 | — | 差集中未出现 → 删除时该目录不存在，**无损失** |
| `server_A/README.md`、`server_A/server/README.md`、`server_A/server/README_v2.md` | 文档 | ✅ 属 14cc5b19 的归档重命名，新位置已在 HEAD 中 | 无损失 |
| `server_A/docs/*.md`、`server_A/docs/docs/*.md` | 文档 | ✅ 同上，属"误建重复副本"清理与归档 | 无损失 |

**关于回收站不可恢复的关键发现**：15:14 批次中 42 个 `$R` 文件（回收站中原文件的内容副本）**大小合计为 0 字节**。也就是说该删除实现只写入了 `$I` 元数据（原始路径），没有保留文件内容。因此 `hajimi.db` 与 `runs.jsonl` 的历史数据无法通过回收站取回。

### 6.1 逐 worktree 落盘：`data/` 是本地产物，各 worktree 各写各的

`eval_telemetry.py` 的落盘位置按 `__file__` 计算，因此遥测数据按 worktree 独立存放：

```python
_REPO_ROOT   = Path(__file__).resolve().parents[3]   # 该文件所在 worktree 的根
_DEFAULT_DIR = _REPO_ROOT / "server_A" / "data" / "eval"
```

`server_A/.gitignore` 第 6、7 行（`data/hajimi.db*`、`data/eval/`）已把 `data/` 排除在版本控制外，HEAD 中 0 个跟踪文件——**这正是它不会被 git 补回来的原因**。本次删除的 380 条全部位于 `hajimi-eval\...` 之下，主仓库不在影响范围内。实测结果：

| 检查项 | 主仓库 `Fuzzy-Visual-Assisted-Question-Answering-System` | 结论 |
|---|---|---|
| `server_A/data/hajimi.db` | 存在，266 240 B（2026-09-01 16:25） | ✅ 完好 |
| `server_A/data/hajimi.db-shm` | 存在，32 768 B（2026-09-03 11:51） | ✅ 完好 |
| `server_A/data/hajimi.db-wal` | 存在，2 278 392 B（2026-09-03 11:54） | ✅ 完好，且含实质写入 |
| `server_A/data/eval/` | **目录不存在** | ❌ 主仓库也未生成过遥测 |
| 全盘搜索 `runs.jsonl`（`D:\HAJIMI_B`、`%LOCALAPPDATA%\HAJIMI`） | 0 结果 | ❌ 无副本可用 |

**结论**：数据库基线未丢失（主仓库那份完好，可直接用于对照）；响应时间 / 准确率的遥测基线（`runs.jsonl`）**确认丢失，只能重跑重建**。后续跑分建议把 `server_A/data/eval/` 纳入定期备份，因为它既不受版本控制保护，也不在回收站里留内容。

## 7. 附录：取证命令（可复用）

```bat
:: 1) 定位删除时间点：回收站条目按时间分布
ls -lt --time-style=long-iso "D:\$RECYCLE.BIN\<SID>" | awk '{print $6, substr($7,1,5)}' | uniq -c | head -15

:: 2) 解码 $I 元数据拿到原始路径（UTF-16LE，去掉 NUL 即得 ASCII）
tr -d '\000' < "D:\$RECYCLE.BIN\<SID>\$IXXXX" | grep -ao "D:.HAJIMI_B[A-Za-z0-9_.\\/-]*"

:: 3) 差集：丢失的未跟踪文件
git ls-files > tracked.txt
grep -vxF -f tracked.txt lost_relative_paths.txt

:: 4) 确认回收站是否保留内容
ls -lt --time-style=long-iso "D:\$RECYCLE.BIN\<SID>" | awk '$NF ~ /^\$R/ {c++; s+=$5} END{print c, s}'
```

> 注：本机 Bash 的 coreutils（ls / grep / cp / wc）不可用，需显式调用
> `C:\Users\<user>\.workbuddy\binaries\PortableGit\versions\1.2.0\usr\bin\*.exe`。
> PowerShell 若 stdout 不回传，改用「输出写文件 + 文件读取」绕过。
