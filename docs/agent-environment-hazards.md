# Agent 执行环境风险：工作区批量文件静默丢失

> 适用范围：在 Windows 端对 `hajimi-eval` 工作区执行 git 操作的任何 agent（Codex / WorkBuddy / 手工终端）。
> 本文自包含，不依赖其他文档即可理解与处置。
> 阅读顺序建议：§1 事故 → §4 修复（若已中招）→ §5 纪律 → §8 网络限制。

## 1. 事故概述

**时间**：2026-09-23 15:14（Asia/Shanghai）
**触发命令**：`git reset --hard origin/master`（`hajimi-eval` 从 **`60a9943c`** 快进到 `14cc5b19`；`60a9943c` 取自 reflog 15:14:03，**不是**更早的 `1459a290`，见 §6.3）
**现象**：`server_A/` 下受跟踪文件中 **291 个从磁盘消失**（`git status` 显示为 291 条 ` D`）；磁盘上 `server_A` 全树仅存 2 个 `.py` 文件（即本次有变更、被写回的那两个测试文件）。注：事故当时 `server_A/` 受跟踪文件为 304 个，此处仅为叙事，**不是校验基准**——任何绝对数量都会随仓库演进过期，校验请用 §4 的自洽写法。
**结果**：`git checkout-index -a -f` 全额恢复，四条验收通过，Sidecar 冒烟通过

关键定性：**这不是 git 的行为，也不是人为删除或杀毒软件。** 在已排除的候选中，与全部 9 条证据一致的解释是：执行层（agent 沙箱的文件系统代理）在落地 git 的写盘请求时，采用了「整目录删除 + 只写回差异文件」的实现。**该机理为推断，未被直接观测证实**（见 §2）。

## 2. 机理（推断）

> **本节为推断。** 未抓到代理的行为日志，**本节全部内容均为推断**；步骤 2 的「（推断）」标注仅为强调，不代表其余条目已获证实。
> 例外：**§3 证据 10** 是唯一接近直接观测的一条——它同时具备"删除痕迹"与"幸存结果"，直接证明「先删除、再写回」这个动作序列发生过。但它只覆盖 2 个文件，**不能证明"整目录删除"这个动作本身**，因此步骤 1 的整体范围仍属推断。§3 的 10 条证据只用于说明"该推断与观测一致"，不构成完整证明。

代理的写盘方式为「**先删除，再写入**」：

| 步骤 | 代理的行为 | 后果 |
|---|---|---|
| 1 | 把目标整棵子树删除（走 Windows 回收站 API，故进入 `$RECYCLE.BIN`） | 未跟踪文件（`__pycache__`/`.pyc`）一并被带走——git 绝不会碰未跟踪文件，这是"删除者不是 git"的最直接证据 |
| 2 | （推断）只把本次有差异的文件写回（本例精确为 **13 个**，核对过程见 §6.3） | 其余未变更文件不会被写回，留在回收站 |
| 3 | 索引仍认为这些文件存在且内容匹配（stat 缓存未失效） | `git status` 此前显示"干净"，问题被隐藏到下次操作才暴露 |

**风险面理论上不止于 `reset --hard`**：`git checkout`、`git switch`、`git stash`、`git restore`、大范围 `git checkout -- <path>` 等会批量重写工作区的操作，理论上适用同一机理；**但本次仅在 `reset --hard` 上得到观测**，其余命令未经验证，请按"可能"而非"必然"对待。

**旁证（推断）**：`.git\worktrees\hajimi-eval\index.lock`、`AUTO_MERGE.lock`、`packed-refs.lock` 在 15:16 / 15:19×4 / 15:22 反复进入回收站——这些是 git 自身的锁文件，只可能是写盘时被一并删除。该现象**提示**每一次文件写入都可能经过这条删除路径；写单个文件时无害，整目录重写时就会静默吞掉未变更文件。

## 3. 证据链

| # | 证据 | 结论 |
|---|---|---|
| 1 | 回收站 `$I*` 元数据解码：338 个条目，解码去重后 **332 条路径**（`hajimi-eval` 下 329 + 主仓库 `.git` 下 3），时间戳**全部集中在 2026-09-23 15:14**（同一批次另有 15:13 的 2 条） | 删除是**一次性**发生的，时刻与 `reset --hard` 重合（reflog：15:14:03 checkout / 15:14:29 reset） |
| 2 | 回收站时间分布中 **09-16 ～ 09-22 无任何条目**；09-15 只有 B1 校准期的零星条目 | 排除"09-15 之后被人手工删除/ `git clean` 过"的假设 |
| 3 | `git diff --name-status 60a9943c 14cc5b19 -- server_A/` 仅 **22 条路径**（9D / 3M / 10R），全仓 31 文件（3A / 9D / 9M / 10R） | reset 本不该触碰 291 个文件。基准必须是 `60a9943c`；若误用更早的 `1459a290`，该命令会输出 30 条 / 全仓 39 文件，与此处数字不符——见 §6.3 |
| 4 | 被删的 `defaults.py` / `run_eval.py` / `providers.py` / `fonts.py` / `test_perception.py` 在 `14cc5b19` 中均存在（`cat-file -e` 通过） | 这些文件属于"不应被删"的范畴 |
| 5 | 回收站中存在未跟踪路径 `__pycache__` / `*.pyc` / `server_A\data\*` | 非 git 行为（git 不动未跟踪文件，且 git 的 unlink 不会进回收站） |
| 6 | Windows Defender：`Get-MpThreatDetection` 为空；`wevtutil` 唯一 1116 事件是 `SakuraFrpLauncher.exe`（`Trojan:Win32/Kepavll!rfn`），0 条 1117 | **排除杀毒误报** |
| 7 | `D:\` 为普通本地盘（含 `$RECYCLE.BIN`、`System Volume Information`），无同步目录指向 `D:\HAJIMI_B` | **排除云同步** |
| 8 | PowerShell / shell 历史中无任何针对 `server_A` 或 `hajimi-eval` 的删除命令 | **排除历史清理命令** |
| 9 | 幸存文件恰好是本次差异文件（详见 §6.3 的 13 个清单） | 与"只写回差异文件"的模型吻合（支持，非证明） |
| 10 | 13 个应写回文件中，`test_calib.py` 与 `test_waa_pilot.py` **既出现在回收站 15:14 批次中，又在磁盘上完好存在** | **最接近直接观测的一条**：这两个文件删除前就在磁盘上（属 `M` 类），被删除后又被写回，因此同时留下删除痕迹与磁盘副本。它直接证明了「先删除、再写回」这一动作序列确实发生过——区别于其余只证明"文件消失了"的间接证据 |

## 4. 修复方法

`git checkout-index -a -f` 是**确定性修复**：它直接按索引写盘，不读工作区状态，因此绕开 stat 缓存问题；只补回缺失的受跟踪文件，不动未跟踪文件（`.env` 因此安全）。

> **Shell 兼容性**：验收 **1、2 为纯 git 命令**，任何 shell（cmd / bash / PowerShell）都能直接跑，零 coreutils 依赖。验收 **3、4 用到 `ls`**，cmd 等价写法为 `dir`；若本机 Bash 的 coreutils 不可用，见 §7 的 PortableGit 显式路径。

```bash
cd /d D:\HAJIMI_B\hajimi-eval
git status --porcelain          # 先确认为纯 D 条目（无 M / A / ?? 未提交改动）
git checkout-index -a -f
```

**验收四条，全过才算成功：**

```bash
# 1) 工作区干净
git status --porcelain                  # 必须空输出

# 2) 索引与 HEAD 自洽（纯 git，不依赖 coreutils；server_A 增减文件后依然有效）
git diff --cached --name-only      # 空 = 索引 == HEAD
git diff --name-only               # 空 = 工作区 == 索引
# 两条均空即自洽。限定目录时在末尾加 -- server_A/
# 说明：验收 1 的 status 为空已蕴含这两条，此处为显式交叉验证

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
| 1 | **只需快进时用 `git merge --ff-only origin/master`，不用 `reset --hard`** | 本例两者效果完全相同，但前者不会丢弃本地改动（分叉时直接拒绝）。注意：它**不解决**写盘缺陷——批量写盘风险与 `--hard` 相同，仍须遵守纪律 2，见 §5.1 |
| 2 | **破坏性 git 操作一律在 agent 沙箱外的终端执行**（系统 PowerShell / VS Code 终端） | 沙箱写盘即本文所述缺陷；判据见 §5.1 |
| 3 | **任何写工作区的 git 命令之后立即例行 `git status --porcelain`**；非空且为纯 `D` 条目 = 缺陷又发作了 | 唯一能及时发现的手段。只读命令（`status` / `log` / `diff`）之后不必重复检查 |
| 4 | **把工作区交给 agent 前先确认 `git status` 干净且文件齐全** | 否则 agent 会在残缺工作区上继续工作 |

### 5.1 纪律 2 的判据：什么算"破坏性"

**判据是"会不会一次性写入大量文件"，不是"会不会丢改动"。** 这是两个独立维度，必须分开看——混淆二者会导致把 `merge --ff-only` 误判为安全：

| 命令 | 批量重写工作区 | 丢弃本地改动 | 触发写盘缺陷 |
|---|---|---|---|
| `reset --hard` | 是 | **是**（强制丢弃） | **是** |
| `merge --ff-only` | 是（快进时 checkout 全部差异文件） | 否（分叉时直接拒绝） | **是，与 `--hard` 相同** |
| `checkout -- <单个文件>` | 否 | 是（该文件） | 否 |

因此：**纪律 1 推荐 `--ff-only` 只解决了"不丢改动"这一个问题；批量写盘的风险两者完全一样**，`--ff-only` 同样应在沙箱外执行。

```
判据：该命令会不会一次性写入【大量】文件？
  ├─ 会（批量重写工作区）→ 沙箱外执行：
  │    reset --hard / clean / 大范围 checkout·switch·restore /
  │    checkout -- <目录> / stash pop·apply / merge --ff-only（快进时）
  └─ 不会（单个或少量文件）→ 沙箱内安全执行：
       status / log / diff / show / add / commit / fetch / push /
       ls-files / ls-tree / rev-parse / checkout -- <单个文件>
```

单个文件写入无害——§2 的旁证正好印证这一点：`index.lock` 反复进回收站但没造成损失，**损失只发生在整目录重写那一刻**。

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
| ↳ `$I`（路径元数据） | 338 | 解码去重后 **332 条路径** |
| 　　↳ 位于 `hajimi-eval\` 下 | **329** | 本文的损失口径 |
| 　　↳ 位于主仓库 `.git\` 下 | 3 | `packed-refs.lock`、`worktrees\hajimi-eval\{AUTO_MERGE,HEAD}.lock`。**329 + 3 = 332 ✅** |
| ↳ `$R`（内容副本） | 42 | **合计 0 字节** |
| 受跟踪文件丢失（**权威口径**） | **291** | `git status` 的 ` D` 条目数，来自 git 自身观测 |
| ↳ 其中在回收站能找到记录 | **236** | 差额 55 = 回收站记录不完整（与 `$R` 仅 42 条且全 0 字节互相印证） |
| 未跟踪条目丢失 | **93** | = 329 − 236 |
| ↳ `.pyc`（可重建） | 47 | 运行即重建，无损失 |
| ↳ 有价值的数据文件 | 4 | `hajimi.db` / `-shm` / `-wal` / `runs.jsonl`（见 §6.1） |
| ↳ 其余 | 42 | 目录条目与正则噪声（如 `/T`、`y`）。93 − 47 − 4 = 42 ✅ |

**四个口径覆盖范围不同，不可相加。** 三处差额的来源：

- **291 vs 236（差 55）**：291 是 git 观测到的丢失；236 是能在回收站找到删除痕迹的部分。差额说明该删除实现本身的回收站记录不完整（`$R` 仅 42 条且全 0 字节，是同一现象的另一面）。**以 291 为准。**
- **380 vs 332（差 48）**：380 是回收站的文件条目数（`$I` + `$R` 各占一份），332 是解码出的去重路径数。两者统计对象不同，不存在加减关系。
- **未跟踪条目 112 → 95 → 93，两次修正**：
  - `112`（错）：仅用**新 HEAD 索引**做差集，把 `14cc5b19` 正常删除/重命名的受跟踪文件误算成"未跟踪"。改用**删除前后索引的并集**（`14cc5b19` 785 条 ∪ `60a9943c` 791 条 = 804 条）后修正为 `95`。
  - `95 → 93`：`95` 是按"路径字符串含 `hajimi-eval`"筛选的结果，误含了主仓库 `.git\worktrees\hajimi-eval\` 下的 2 个 lock 文件。改用**路径前缀严格等于 `D:\HAJIMI_B\hajimi-eval\`** 后修正为 `93`（329 = 236 + 93 ✅）。

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
| 47 个 `.pyc`（`__pycache__/`） | Python 字节码缓存 | ✅ 运行即重建 | 无损失 |
| 42 个目录条目与正则噪声 | 目录本身进入回收站；另有少数正则误提取项 | ✅ 随文件重建 | 无损失 |
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

### 6.3 应写回 13 个：数字闭环，兼答"差额 8"

复核时发现一个**极易踩的坑**：reset 前的 HEAD 是 **`60a9943c`**，不是 `1459a290`。

```
reflog:
  14cc5b19 HEAD@{15:14:29}  reset: moving to origin/master
  60a9943c HEAD@{15:14:03}  checkout: moving from master to master   ← reset 前的真实 HEAD
```

`1459a290` 是 `60a9943c` 的**更早祖先**（两者之间夹着 4 个 B1 校准提交：`da0d7cff`、`c53de7b6`、`f31a64e8`、`60a9943c`）。用错基准会直接算错应写回数：

| 基准 | `server_A/` 下变更行数 | 构成 | 应写回（`M` + `R` 的新路径） |
|---|---|---|---|
| `1459a290 → 14cc5b19`（**错误基准**） | 30 | 6A + 9D + 5M + 10R | 21 |
| `60a9943c → 14cc5b19`（**正确基准**） | 22 | 9D + 3M + 10R | **13** |

**差额 8 条的精确来源**——全部是 `1459a290 → 60a9943c` 之间那 4 个 B1 校准提交引入、且在 `60a9943c` 时**已经落地**的变更，因此在本次 reset 中不属于"差异文件"：

```
A  server_A/eval/calib_evidence/agent_log_2026-09-15.md
A  server_A/eval/calib_evidence/signoff_b1.md
A  server_A/eval/calib_evidence/task1_notepad_type_save_do.ps1
A  server_A/eval/calib_evidence/task2_explorer_rename_file_do.ps1
A  server_A/eval/calib_evidence/task3_explorer_new_folder_do.ps1
A  server_A/eval/calib_evidence/task4_notepad_type_chinese_do.ps1
M  server_A/eval/tasks/seed.json
M  server_A/server/tests/test_eval_tasks.py
```

**闭环验证（三个数字互相咬合）：**

```
14cc5b19 中 server_A/ 受跟踪文件数        = 304
应写回（3 个 M + 10 个 R 的新路径）        =  13
304 − 291（消失）                          =  13   ✅ 与应写回数完全相等
```

**因此 §6.0 标为权威口径的 291 无需修正。** 本文不采纳"缺失应为 283"的推算——那是基于错误基准 `1459a290` 得出的；正确基准下 21 应为 13，与 304−291 严丝合缝。

**13 个应写回文件的完整清单**（均位于 `server_A/` 下）：

| 类别 | 数量 | 路径 |
|---|---|---|
| `M`（修改） | 3 | `server/server/docs/archive/legacy-L4/README.md`、`server/tests/test_calib.py`、`server/tests/test_waa_pilot.py` |
| `R` 的新路径（重命名目标） | 10 | `server/docs/archive/legacy-L4/server_A-layer/` 下的 `README.md`、`docs/{API-CONTRACT, BACKEND-CHECKLIST, DEV-GUIDE, UI-SPEC, api-admin-users, api-auth, api-reference}.md`、`server/{README, README_v2}.md` |

其中 `test_calib.py` 与 `test_waa_pilot.py` **同时存在于回收站与磁盘上**——这正是 §3 证据 10，也是"先删除、再写回"最接近直接观测的一条证据。

> **本次基准修正的波及范围**：同一处基准混淆（`1459a290` vs `60a9943c`）曾同时污染三处，均已修正为 `60a9943c`——**§1 触发命令的 from-commit**、**§3 证据 3 的命令行**（其"全仓 31 文件"其实一直属于 `60a9943c` 口径，只有 hash 写错）、以及本文 §6.3 的应写回数。核对时可用一条命令自查：`git diff --name-status <基准> 14cc5b19 -- server_A/ | wc -l`，**输出 22 才是正确基准**。

## 7. 附录：取证命令（可复用）

**第 0 步：拿到当前用户的 SID**（回收站目录名就是它，后面全部用到 `<SID>`）：

```bat
whoami /user
:: 或直接列出
dir /b "D:\$RECYCLE.BIN"
```

取证命令**同时给出 bash 与 PowerShell 两套等价写法**。本机 Bash 的 coreutils 常常不可用，PowerShell 更可靠；两者都跑不了时再退到 PortableGit 显式路径。

### 1) 定位删除时间点：回收站条目按时间分布

```bash
ls -lt --time-style=long-iso "D:/\$RECYCLE.BIN/<SID>" | awk '{print $6, substr($7,1,5)}' | uniq -c | head -15
```

```powershell
Get-ChildItem "D:\`$RECYCLE.BIN\<SID>" -Force |
  Group-Object {$_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')} |
  Sort-Object Name | Select-Object Count, Name
```

### 2) 解码 `$I` 元数据拿到原始路径

`$I` 是 UTF-16LE。**bash 用 `tr` 去 NUL，不要用 `iconv`**——`iconv` 遇到非法序列会中途停止，只解出前一部分。

```bash
# 单条
tr -d '\000' < "D:/\$RECYCLE.BIN/<SID>/\$IXXXX" | grep -ao "D:.HAJIMI_B[A-Za-z0-9_.\\/-]*"

# 全量（推荐）：一次解出所有 $I，输出即为命令 3 的输入 all_i.txt
cat "D:/\$RECYCLE.BIN/<SID>"/\$I* | tr -d '\000' \
  | grep -ao "D:.HAJIMI_B[A-Za-z0-9_.\\/-]*" | sort -u > all_i.txt
```

> 下文命令 3 的输入统一为 **`all_i.txt`**（本命令全量版的产物）。

```powershell
# 单条
(Get-Content "D:\`$RECYCLE.BIN\<SID>\`$IXXXX" -Encoding Unicode -Raw) -replace "\0","" |
  Select-String -AllMatches "D:\\HAJIMI_B[A-Za-z0-9_.\\/-]*" |
  ForEach-Object { $_.Matches.Value }

# 全量（推荐：一次解出所有 $I，写文件后再读，规避 stdout 不回传）
Get-ChildItem "D:\`$RECYCLE.BIN\<SID>" -Force -Filter '$I*' | ForEach-Object {
  (Get-Content $_.FullName -Encoding Unicode -Raw) -replace "\0",""
} | Out-File -Encoding utf8 all_i.txt
```

### 3) 差集：真正未跟踪的丢失

三个坑（详见 §6.0、§6.3）：

① 索引用**删除前后并集**，否则会把本次正常删除的文件误算成丢失。
② 路径筛选用**严格前缀**，不要用 `grep "hajimi-eval"` 字符串匹配——主仓库 `.git\worktrees\hajimi-eval\` 下的文件会被误纳入。
③ `<旧HEAD>` 必须是**事故发生前那一刻**的 HEAD，用 reflog 取，**不要凭记忆或按分支推断**：

```bash
git reflog --date=iso | head        # 找 reset/checkout 之前的那一行
# 本例：15:14:03 checkout 时的 60a9943c。
# 注意它不是更早的 1459a290——用错基准会多算 8 条，见 §6.3。
```

```bash
grep -a "^D:.HAJIMI_B.hajimi-eval." all_i.txt \
  | sed 's|^D:.HAJIMI_B.hajimi-eval.||' | tr '\\' '/' | sort -u > lost_relative_paths.txt

git ls-tree -r --name-only HEAD        > tracked_new.txt
git ls-tree -r --name-only <旧HEAD>    > tracked_old.txt
cat tracked_new.txt tracked_old.txt | sort -u > tracked_all.txt
grep -vxF -f tracked_all.txt lost_relative_paths.txt
```

```powershell
# 严格前缀筛选 + 转相对路径
Get-Content all_i.txt |
  Where-Object { $_ -like 'D:\HAJIMI_B\hajimi-eval\*' } |
  ForEach-Object { ($_ -replace '^D:\\HAJIMI_B\\hajimi-eval\\','').Replace('\','/') } |
  Sort-Object -Unique | Out-File -Encoding utf8 lost_relative_paths.txt

git ls-tree -r --name-only HEAD     > tracked_new.txt
git ls-tree -r --name-only <旧HEAD> > tracked_old.txt
Get-Content tracked_new.txt, tracked_old.txt |
  Sort-Object -Unique | Out-File -Encoding utf8 tracked_all.txt

# 差集
$t = [System.Collections.Generic.HashSet[string]](Get-Content tracked_all.txt)
Get-Content lost_relative_paths.txt | Where-Object { -not $t.Contains($_) }
```

> 用 `HashSet` 而非 `-notcontains`：后者在大集合上是 O(n²)，条数上千会明显变慢。

### 4) 确认回收站是否保留内容（本例 c=42, s=0 → 内容不可恢复）

```bash
ls -lt --time-style=long-iso "D:/\$RECYCLE.BIN/<SID>" | awk '$NF ~ /^\$R/ {c++; s+=$5} END{print c, s}'
```

```powershell
$r = Get-ChildItem "D:\`$RECYCLE.BIN\<SID>" -Force | Where-Object Name -like '$R*'
"c=$($r.Count) s=$(($r | Measure-Object Length -Sum).Sum)"
```

> **Shell 环境提示**：本机 Bash 的 coreutils（`ls` / `grep` / `cp` / `wc` / **`diff`**）不可用，需显式调用
> `C:\Users\<user>\.workbuddy\binaries\PortableGit\versions\<ver>\usr\bin\*.exe`（版本号随安装而变，按实际目录取）。
> 用 `tr` 而非 `iconv` 解码 `$I`；PowerShell 若 stdout 不回传，改用「输出写文件 + 文件读取」绕过。
> 正因如此，§4 的验收命令 1、2 刻意写成**纯 git**（不依赖任何 coreutils），取证命令则两套都给。

## 8. 沙箱网络限制：网络 git 操作默认被挡，可放行

同一类问题的第二个实例：第一个是写盘（§2），第二个是网络。

**准确表述**：网络 git 操作**默认被沙箱挡**（`~/.ssh/known_hosts` 不可读），需 escalation 放行；**放行后 push / fetch / ls-remote 全部正常**。不要写成"无法推送"。

**实测（2026-09-23）**：

| 操作 | 首次 | 结果 |
|---|---|---|
| `git push origin master`（第 1 次） | 失败：`Host key verification failed`（`known_hosts` Permission denied） | 带 `escalation-approved` 重试一次通过：`14cc5b19..bdd1e7be master -> master` |
| `git push origin master`（第 2、3、4 次） | 权限请求**未获批准** | 未执行，改由人工在沙箱外推送 |
| `git ls-remote origin HEAD` | — | 正常 |
| `git fetch origin master` | — | 正常 |
| `git rev-parse origin/master` | — | 正常，确认为 `bdd1e7be` |

**批准的实际情况**：放行由人工判断，**可能被拒，且被拒是常态**。同一天（2026-09-23）内共 **4 次 `git push`**：第 1 次带 `escalation-approved` 一次通过；**第 2、3、4 次权限请求均未获批准**（沙箱列出的被挡路径为 `~/.ssh/*` 全目录，含 `config`、`id_rsa`、`id_ed25519`、`known_hosts` 等 21 项）。**通过率约 1/4**。

因此**不要假设"一定会放行"**——被拒时把阻塞如实上报即可，不要改用变通手段绕过；真正的解法是下面的首选修复。按此通过率，`grill → spec → implement → review → retro` 这类需要高频网络操作的流程在本环境下基本不可行，**应先解决白名单再开工**。

**对 `ready-for-agent` 的影响**：**取决于白名单是否解决**，两种情形结论相反：

| 情形 | agent 能力 | `ready-for-agent` 语义 |
|---|---|---|
| **白名单已解决** | 网络操作与本地操作无异，push / fetch / 建 issue 全自主 | **不受影响**，按原定义使用 |
| **白名单未解决**（当前状态） | 可完整做到 commit，**push 由人执行**；`gh` 亦不可用 | **受影响**：按 1/4 的通过率，凡需要高频网络操作的流程**不应标为 `ready-for-agent`**（其定义是 "Fully specified, ready for an AFK agent"，而一个推不上去的 agent 不是 fully AFK）。此时该标签应理解为「**agent 可完成到 commit，push 由人执行**」 |

纪律中应写明：**网络 git 操作预期会触发一次批准且可能被拒，属正常流程，不要视为阻塞、也不要为此改用变通手段绕过沙箱。**

**首选修复**：把 `~/.ssh/` 加入沙箱允许读取路径（只读密钥与 `known_hosts`，不写入，风险面小），以消除每次批准。

**备选**：改用 HTTPS + PAT，凭据走 Windows Credential Manager——但该方案同样可能被沙箱挡，需实测后再决定。
