# Agent 执行环境风险：工作区批量文件静默丢失

> 适用范围：在 Windows 端对 `hajimi-eval` 工作区执行 git 操作的任何 agent（Codex / WorkBuddy / 手工终端）。
> 本文自包含，不依赖其他文档即可理解与处置。
> 阅读顺序建议：§1 事故 → §4 修复（若已中招）→ §5 纪律 → §8 网络限制。

## 1. 事故概述

**时间**：2026-09-23 15:14（Asia/Shanghai）
**触发命令**：`git reset --hard origin/master`（`hajimi-eval` 从 `1459a290` 快进到 `14cc5b19`）
**现象**：`server_A/` 下 304 个受跟踪文件中 **291 个从磁盘消失**（`git status` 显示为 291 条 ` D`）；磁盘上 `server_A` 全树仅存 2 个 `.py` 文件（即本次有变更、被写回的那两个测试文件）
**结果**：`git checkout-index -a -f` 全额恢复，四条验收通过，Sidecar 冒烟通过

关键定性：**这不是 git 的行为，也不是人为删除或杀毒软件。** 在已排除的候选中，与全部 9 条证据一致的解释是：执行层（agent 沙箱的文件系统代理）在落地 git 的写盘请求时，采用了「整目录删除 + 只写回差异文件」的实现。**该机理为推断，未被直接观测证实**（见 §2）。

## 2. 机理（推断）

> **本节为推断。** 未抓到代理的行为日志，全部为间接证据。凡标注「（推断）」的条目均属推论，不是已证实的事实；§3 的 9 条证据只用于说明"该推断与观测一致"，不构成证明。

代理的写盘方式为「**先删除，再写入**」：

| 步骤 | 代理的行为 | 后果 |
|---|---|---|
| 1 | 把目标整棵子树删除（走 Windows 回收站 API，故进入 `$RECYCLE.BIN`） | 未跟踪文件（`__pycache__`/`.pyc`）一并被带走——git 绝不会碰未跟踪文件，这是"删除者不是 git"的最直接证据 |
| 2 | （推断）只把本次有差异的文件写回（本例 30～41 个） | 其余未变更文件不会被写回，留在回收站 |
| 3 | 索引仍认为这些文件存在且内容匹配（stat 缓存未失效） | `git status` 此前显示"干净"，问题被隐藏到下次操作才暴露 |

**风险面理论上不止于 `reset --hard`**：`git checkout`、`git switch`、`git stash`、`git restore`、大范围 `git checkout -- <path>` 等会批量重写工作区的操作，理论上适用同一机理；**但本次仅在 `reset --hard` 上得到观测**，其余命令未经验证，请按"可能"而非"必然"对待。

**旁证**：`.git\worktrees\hajimi-eval\index.lock`、`AUTO_MERGE.lock`、`packed-refs.lock` 在 15:16 / 15:19×4 / 15:22 反复进入回收站，说明**每一次文件写入都经过这条删除路径**；写单个文件时无害，整目录重写时就会静默吞掉未变更文件。

## 3. 证据链

| # | 证据 | 结论 |
|---|---|---|
| 1 | 回收站 `$I*` 元数据解码：338 个条目（解码去重后 331 条路径指向 `hajimi-eval`），时间戳**全部集中在 2026-09-23 15:14**（同一批次另有 15:13 的 2 条） | 删除是**一次性**发生的，时刻与 `reset --hard` 重合（reflog：15:14:03 checkout / 15:14:29 reset） |
| 2 | 回收站时间分布中 **09-16 ～ 09-22 无任何条目**；09-15 只有 B1 校准期的零星条目 | 排除"09-15 之后被人手工删除/ `git clean` 过"的假设 |
| 3 | `git diff --name-status 1459a290 14cc5b19 -- server_A/` 仅 **22 条路径**（9D / 3M / 10R），全仓 31 文件 | reset 本不该触碰 291 个文件 |
| 4 | 被删的 `defaults.py` / `run_eval.py` / `providers.py` / `fonts.py` / `test_perception.py` 在 `14cc5b19` 中均存在（`cat-file -e` 通过） | 这些文件属于"不应被删"的范畴 |
| 5 | 回收站中存在未跟踪路径 `__pycache__` / `*.pyc` / `server_A\data\*` | 非 git 行为（git 不动未跟踪文件，且 git 的 unlink 不会进回收站） |
| 6 | Windows Defender：`Get-MpThreatDetection` 为空；`wevtutil` 唯一 1116 事件是 `SakuraFrpLauncher.exe`（`Trojan:Win32/Kepavll!rfn`），0 条 1117 | **排除杀毒误报** |
| 7 | `D:\` 为普通本地盘（含 `$RECYCLE.BIN`、`System Volume Information`），无同步目录指向 `D:\HAJIMI_B` | **排除云同步** |
| 8 | PowerShell / shell 历史中无任何针对 `server_A` 或 `hajimi-eval` 的删除命令 | **排除历史清理命令** |
| 9 | 幸存文件恰好是本次差异文件（`test_calib.py`、`test_waa_pilot.py`） | 与"只写回差异文件"的模型吻合（支持，非证明） |

## 4. 修复方法

`git checkout-index -a -f` 是**确定性修复**：它直接按索引写盘，不读工作区状态，因此绕开 stat 缓存问题；只补回缺失的受跟踪文件，不动未跟踪文件（`.env` 因此安全）。

> 以下命令为 **bash** 语法（`ls`、`wc`、`diff` 在 cmd 中不存在）。若本机 Bash 的 coreutils 不可用，见 §7 的 PortableGit 显式路径；cmd 等价写法：`dir server_A\server\main.py`。

```bash
cd /d D:\HAJIMI_B\hajimi-eval
git status --porcelain          # 先确认为纯 D 条目（无 M / A / ?? 未提交改动）
git checkout-index -a -f
```

**验收四条，全过才算成功：**

```bash
# 1) 工作区干净
git status --porcelain                  # 必须空输出

# 2) 索引与 HEAD 自洽（不依赖任何魔法数字，server_A 增减文件后依然有效）
diff <(git ls-files server_A/ | sort) <(git ls-tree -r --name-only HEAD server_A/ | sort)
# 空输出 = 一致。若确需绝对数量，现场取基准值：
# git ls-tree -r --name-only HEAD server_A/ | wc -l

# 3) 关键文件在位
ls server_A/server/main.py server_A/server/routes/demo.py server_A/server/services/executor/engine.py

# 4) 校准证据齐全（6 份）
ls server_A/eval/calib_evidence/
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
| 1 | **只需快进时用 `git merge --ff-only origin/master`，不用 `reset --hard`** | 本例两者效果完全相同，但前者无破坏性选项 |
| 2 | **破坏性 git 操作一律在 agent 沙箱外的终端执行**（系统 PowerShell / VS Code 终端） | 沙箱写盘即本文所述缺陷 |
| 3 | **每次 git 操作后例行 `git status --porcelain`**；非空且为纯 `D` 条目 = 缺陷又发作了 | 唯一能及时发现的手段 |
| 4 | **把工作区交给 agent 前先确认 `git status` 干净且文件齐全** | 否则 agent 会在残缺工作区上继续工作 |

### 5.1 纪律 2 的判据：什么算"破坏性"

判断一个 git 命令是否需要在沙箱外执行，只看一件事：

```
它是否会重写工作区中【你没有修改过】的文件？
  ├─ 会   → 破坏性，沙箱外执行：
  │        reset --hard / clean / 大范围 checkout·switch·restore /
  │        checkout -- <目录> / stash pop·apply（可能覆盖工作区）
  └─ 不会 → 沙箱内安全执行：
           status / log / diff / show / add / commit / fetch / push /
           ls-files / ls-tree / rev-parse / merge --ff-only
```

判断"是否只需快进"（是则用 `--ff-only`，不要用 `--hard`）：

```bash
git fetch origin master
git rev-list --count HEAD..origin/master    # >0  = 远端领先，可以快进
git rev-list --count origin/master..HEAD    # 必须 =0 才能快进；>0 说明本地有分叉，需人工决策
```

## 6. 已确认的数据损失（git 补不回来）

### 6.0 口径表（先读这一张，否则数字对不上）

| 口径 | 数量 | 定义 |
|---|---|---|
| 回收站 15:14 批次总条目 | **380** | = `$I` 338 + `$R` 42 |
| ↳ `$I`（路径元数据） | 338 | 解码去重后 332 条路径（`hajimi-eval` 331 + 主仓库 `.git` 3，含 2 条正则噪声） |
| ↳ `$R`（内容副本） | 42 | **合计 0 字节** |
| 受跟踪文件丢失（**权威口径**） | **291** | `git status` 的 ` D` 条目数，来自 git 自身观测 |
| ↳ 其中在回收站能找到记录 | 236 | 差额 55 = 回收站记录不完整（与 `$R` 仅 42 条且全 0 字节互相印证） |
| 未跟踪条目丢失 | 95 | = 331 − 236 − 噪声 |
| ↳ 目录条目 | 35 | 目录本身也进回收站，不是文件 |
| ↳ 真实文件 | 60 | 其中 51 个 `.pyc`（可重建）+ 4 个数据文件 + 若干边界项 |

**三个口径覆盖范围不同，不可相加。** 两处差额的来源：

- **291 vs 236（差 55）**：291 是 git 观测到的丢失；236 是能在回收站找到删除痕迹的部分。差额说明该删除实现本身的回收站记录不完整（`$R` 仅 42 条且全 0 字节，是同一现象的另一面）。**以 291 为准。**
- **旧口径 112 → 修正为 95**：112 是仅用**新 HEAD 索引**做差集的结果，把 `14cc5b19` 正常删除/重命名的受跟踪文件误算成了"未跟踪"。改用**删除前后索引的并集**（`14cc5b19` 785 条 ∪ `60a9943c` 791 条 = 804 条）后，修正为 95。

正确算法：

```bash
git ls-tree -r --name-only HEAD        > tracked_new.txt   # 删除后
git ls-tree -r --name-only 60a9943c    > tracked_old.txt   # 删除前
cat tracked_new.txt tracked_old.txt | sort -u > tracked_all.txt
grep -vxF -f tracked_all.txt lost_relative_paths.txt        # = 真正未跟踪的丢失
```

### 6.1 真正有价值的损失

| 路径 | 性质 | 可否重建 | 现状 |
|---|---|---|---|
| `server_A/data/hajimi.db`（含 `-shm` / `-wal`） | SQLite，7 张表（用户 / 事务 / 步骤日志 / 反馈 / 失败 / 红线日志 / 系统配置） | ⚠️ 本 worktree 副本不可恢复，**主仓库副本完好** | 见 6.2 |
| `server_A/data/eval/runs.jsonl` | 评测跑分原始结果（响应时间 / 准确率基线） | ❌ 全盘无副本 | **确认丢失** |
| 51 个 `.pyc`（`__pycache__/`） | Python 字节码缓存 | ✅ 运行即重建 | 无损失 |
| 35 个目录条目 | 目录本身（非文件） | ✅ 随文件重建 | 无损失 |
| `server_A/eval/results/*.jsonl` | 跑分原始结果 | — | 差集中未出现 → 删除时该目录不存在，**无损失** |
| `server_A/README.md`、`server_A/server/README.md`、`server_A/server/README_v2.md` | 文档 | ✅ 属 14cc5b19 的归档重命名，新位置已在 HEAD 中 | 无损失 |
| `server_A/docs/*.md`、`server_A/docs/docs/*.md` | 文档 | ✅ 同上，属"误建重复副本"清理与归档 | 无损失 |

**关于回收站不可恢复的关键发现**：15:14 批次中 42 个 `$R` 文件（回收站中原文件的内容副本）**大小合计为 0 字节**。该删除实现只写入了 `$I` 元数据（原始路径），没有保留文件内容。因此 `hajimi.db` 与 `runs.jsonl` 的历史数据无法通过回收站取回。

### 6.2 逐 worktree 落盘：`data/` 是本地产物，各 worktree 各写各的

`eval_telemetry.py` 的落盘位置按 `__file__` 计算，因此遥测数据按 worktree 独立存放：

```python
_REPO_ROOT   = Path(__file__).resolve().parents[3]   # 该文件所在 worktree 的根
_DEFAULT_DIR = _REPO_ROOT / "server_A" / "data" / "eval"
```

`server_A/.gitignore` 第 6、7 行（`data/hajimi.db*`、`data/eval/`）已把 `data/` 排除在版本控制外，HEAD 中 0 个跟踪文件——**这正是它不会被 git 补回来的原因**。本次删除的条目全部位于 `hajimi-eval\...` 之下，主仓库不在影响范围内。实测结果：

| 检查项 | 主仓库 `Fuzzy-Visual-Assisted-Question-Answering-System` | 结论 |
|---|---|---|
| `server_A/data/hajimi.db` | 存在，266 240 B（2026-09-01 16:25） | ✅ 完好 |
| `server_A/data/hajimi.db-shm` | 存在，32 768 B（2026-09-03 11:51） | ✅ 完好 |
| `server_A/data/hajimi.db-wal` | 存在，2 278 392 B（2026-09-03 11:54） | ✅ 完好，且含实质写入 |
| `server_A/data/eval/` | **目录不存在** | ❌ 主仓库也未生成过遥测 |
| 全盘搜索 `runs.jsonl`（`D:\HAJIMI_B`、`%LOCALAPPDATA%\HAJIMI`） | 0 结果 | ❌ 无副本可用 |

**结论**：数据库基线未丢失（主仓库那份完好，可直接用于对照）；响应时间 / 准确率的遥测基线（`runs.jsonl`）**确认丢失，只能重跑重建**。后续跑分建议把 `server_A/data/eval/` 纳入定期备份，因为它既不受版本控制保护，也不在回收站里留内容。

## 7. 附录：取证命令（可复用）

**第 0 步：拿到当前用户的 SID**（回收站目录名就是它，后面全部用到 `<SID>`）：

```bat
whoami /user
:: 或直接列出
dir /b "D:\$RECYCLE.BIN"
```

以下为 **bash** 语法：

```bash
# 1) 定位删除时间点：回收站条目按时间分布
ls -lt --time-style=long-iso "D:/\$RECYCLE.BIN/<SID>" | awk '{print $6, substr($7,1,5)}' | uniq -c | head -15

# 2) 解码 $I 元数据拿到原始路径（UTF-16LE；用 tr 去 NUL，不要用 iconv ——
#    iconv 遇到非法序列会中途停止，导致只解出前一部分）
tr -d '\000' < "D:/\$RECYCLE.BIN/<SID>/\$IXXXX" | grep -ao "D:.HAJIMI_B[A-Za-z0-9_.\\/-]*"

# 3) 差集：真正未跟踪的丢失（务必用删除前后的索引并集，见 §6.0）
git ls-tree -r --name-only HEAD     > tracked_new.txt
git ls-tree -r --name-only <旧HEAD> > tracked_old.txt
cat tracked_new.txt tracked_old.txt | sort -u > tracked_all.txt
grep -vxF -f tracked_all.txt lost_relative_paths.txt

# 4) 确认回收站是否保留内容（本例 c=42, s=0 → 内容不可恢复）
ls -lt --time-style=long-iso "D:/\$RECYCLE.BIN/<SID>" | awk '$NF ~ /^\$R/ {c++; s+=$5} END{print c, s}'
```

> **Shell 环境提示**：本机 Bash 的 coreutils（`ls` / `grep` / `cp` / `wc`）不可用，需显式调用
> `C:\Users\<user>\.workbuddy\binaries\PortableGit\versions\<ver>\usr\bin\*.exe`（版本号随安装而变，按实际目录取）。
> 用 `tr` 而非 `iconv` 解码 `$I`；PowerShell 若 stdout 不回传，改用「输出写文件 + 文件读取」绕过。

## 8. 沙箱网络限制：网络 git 操作默认被挡，可放行

同一类问题的第二个实例：第一个是写盘（§2），第二个是网络。

**准确表述**：网络 git 操作**默认被沙箱挡**（`~/.ssh/known_hosts` 不可读），需 escalation 放行；**放行后 push / fetch / ls-remote 全部正常**。不要写成"无法推送"。

**实测（2026-09-23）**：

| 操作 | 首次 | 结果 |
|---|---|---|
| `git push origin master` | 失败：`Host key verification failed`（`known_hosts` Permission denied） | 带 `escalation-approved` 重试一次通过：`14cc5b19..bdd1e7be master -> master` |
| `git ls-remote origin HEAD` | — | 正常 |
| `git fetch origin master` | — | 正常 |
| `git rev-parse origin/master` | — | 正常，确认为 `bdd1e7be` |

**批准的实际情况**：放行由人工判断，**可能被拒**。同一天（2026-09-23）内两次 `git push`：第一次带 `escalation-approved` 一次通过；第二次权限请求被拒（沙箱列出的被挡路径为 `~/.ssh/*`）。因此**不要假设"一定会放行"**——被拒时把阻塞如实上报即可，不要改用变通手段绕过；真正的解法是下面的首选修复。

**影响**：agent 可以完整做到 commit，**push 需要一次批准**。因此 `ready-for-agent` 的语义**不受影响**，但纪律中应写明：**网络 git 操作预期会触发一次批准，属正常流程，不要视为阻塞、也不要为此改用变通手段绕过沙箱。**

**首选修复**：把 `~/.ssh/` 加入沙箱允许读取路径（只读密钥与 `known_hosts`，不写入，风险面小），以消除每次批准。

**备选**：改用 HTTPS + PAT，凭据走 Windows Credential Manager——但该方案同样可能被沙箱挡，需实测后再决定。
