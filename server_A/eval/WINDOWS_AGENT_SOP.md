# Windows Agent 自动测试 SOP（评测台执行手册 · agent 版）

> 目的：让 Windows 端的 Codex/Claude Code 等 agent 按本手册**自动完成评测台的全部机械步骤**，
> 并在需要人工裁决处**明确停下来等签收**。配套：`HOWTO_WINDOWS.md`（人工版）、`decision_rules.md`（拍板规则）。
>
> ⚠️ 铁律（防自欺）：**校准的人审签收不可省**——agent 只做执行与证据收集，
> 置位 `calibrated:true` 必须有人对签收表点确认。**未校准任务分数禁入汇报口径。**

---

## 0. 角色边界（先读，决定每一步是"自动"还是"停下"）

| 步骤 | agent 动作 | 停等人工? |
|---|---|---|
| 环境准备（分支/venv/sidecar） | 执行 | 否 |
| calib --show / --setup / --check / --selftest | 执行并收集证据 | 否（但 selftest 的"人审"在置位前） |
| **校准两向（真做→PASS / 故意失败→FAIL）** | **执行 + 生成签收表** | **✅ 是：置位前必须人签收** |
| 全量跑分 --repeats 4 + 基线回测 | 执行 | 否 |
| report 对比 + fail_analyzer 缺陷票 | 执行 | 否 |
| **优化项拍板（回滚/合入）** | 出建议清单 | **✅ 是：最终裁决人做** |
| 日常真实任务遥测积累 | 执行 | 否 |

---

## 1. 前置检查（agent 逐项验证并记录）

```powershell
# ① 分支与同步（D: 当前可能 checkout 在 front——评测必须 master 或 worktree）
cd /d D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System
git branch --show-current        # 若是 front：先确认无未提交改动，再 git checkout master && git pull --ff-only origin master
git rev-parse --short HEAD        # 记录评测代码版本（label 用）

# ② 依赖与 key
if (!(Test-Path server_A\server\.venv\Scripts\python.exe)) { echo "需先安装全栈.bat 建 venv" }
if (!(Test-Path server_A\server\.env)) { echo "需配置 server_A\server\.env（DEEPSEEK_API_KEY）" }

# ③ 起 sidecar（评测模式，保持窗口）
cd server_A
server\\.venv\\Scripts\\python -m uvicorn server.main:app --port 8011
# 另开窗口验证：
curl -s http://127.0.0.1:8011/api/demo/health
```

**检查点 C0**：sidecar 就绪 + HEAD 记录后，向用户报"准备就绪，开始 B1 批校准证据收集"。

---

## 2. 阶段 A —— 校准证据收集（agent 自动，机械执行）

对 `HOWTO_WINDOWS.md §9` 的批次清单逐任务执行。**先做 B1（5 条稳定任务）**。

### A1. 看任务与 oracle 语义
```powershell
python -m eval.calib --list
python -m eval.calib notepad_type_save --show   # 逐任务
```
agent 把 `--show` 输出的 INSTRUCTION / setup / cleanup / oracle 谓词**逐条转述进日志**，
作为签收表素材。**若 oracle 语义明显可疑（如判据过松/窗口标题匹配不唯一），停等人工裁决**（检查点 C1），不得自行改 oracle。

### A2. setup + 现场判分（确定性）
```powershell
python -m eval.calib notepad_type_save --setup
python -m eval.calib notepad_type_save --check   # 期望：此阶段大多 FAIL（任务还没做）
```

### A3. 两向执行（真做 / 故意失败）
- **真做一遍**：agent 用**确定性脚本**（PowerShell / pywinauto 直调，**禁止用 LLM 驱动**——校准目标就是独立判据）按 INSTRUCTION 精确执行。
  - B1 稳定任务"真做"可写成可复用脚本：notepad 保存/改名/建文件夹/输入中文 → 落盘 `eval\calib_evidence\b1_<id>_do.ps1`
  - 执行后 `--check` → 必须 PASS。
- **故意失败一遍**：对同一任务**跳过关键动作**（如不点保存）再 `--check` → 必须 FAIL。
- 若两向结果不符（真做 FAIL / 故意失败 PASS）→ **oracle 判据有问题，停等人工**（检查点 C1），禁止凑合。

### A4. 生成签收表
每个任务一条，写 `eval\calib_evidence\signoff_<batch>.md`：
```
## <task_id>  <source>
- INSTRUCTION: <转述>
- 真做: <命令/脚本> → --check <PASS/FAIL>  (期望 PASS)
- 故意失败: <跳过动作> → --check <PASS/FAIL>  (期望 FAIL)
- oracle trace: <粘贴关键谓词行>
- 判定: 两向符合 ✓ / 异常 ✗（异常→C1）
```
**检查点 C1（每任务）**：B1 整批签收表完成后，**停下，把签收表发给用户**，
等用户逐条确认后才执行 `--calib-done`。人工路径置位：
```powershell
python -m eval.calib notepad_type_save --calib-done
```

### A5. gold 任务（若批次含 gold 脚本任务）
有 `calib_gold` 脚本的任务走 gold 路径：
```powershell
python -m eval.calib waa_xxx --selftest      # 五段自动（setup→FAIL断言→gold→PASS断言→cleanup→回FAIL）
python -m eval.calib waa_xxx --calib-done --via-gold
```
gold selftest 全过后**仍要人审签收**（gold 判定的是脚本正确性，不替代 oracle 语义人审）——同上停等 C1。

---

## 3. 阶段 B —— 全量跑分 + 基线回测（全自动）

**B 前提**：批次校准已签收置位。

```powershell
:: 当前批（master）
python eval\run_eval.py --repeats 4 --label master-cal-<HEAD> --only <已校准 id 逗号列表>
:: 或全任务（含未校准，分数只修 oracle 不进口径）：
:: python eval\run_eval.py --repeats 4 --label full-cal-<HEAD>

:: 基线回测（P0 前基线，worktree）
git worktree add ..\hajimi-base 049acc8a
cd /d D:\HAJIMI_B\hajimi-base
server_A\server\.venv\Scripts\python eval\run_eval.py --repeats 4 --label base-p0pre --only <同 id 列表>
cd /d D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System

:: 对比报告
python eval\report.py ..\hajimi-base\eval\results\base-p0pre.jsonl eval\results\master-cal-<HEAD>.jsonl --out eval\results\delta-p0.md
git worktree remove ..\hajimi-base
```
**注意**：基线 worktree 的 venv 缺失——可直接复用主仓库 venv 的 python 路径，
或 worktree 内 `--venv` 指向主仓库（`eval\run_eval.py` 支持时）。agent 如实记录此细节。

**检查点 C2**：报告生成后**向用户呈报 delta**（All-Pass@4 / pass@1 / token 均值），
不自动下"回滚/合入"结论。

---

## 4. 阶段 C —— 归因闭环（agent 出建议，人拍板）

```powershell
python eval\fail_analyzer.py eval\results\master-cal-<HEAD>.jsonl eval\results\defects.jsonl
```
agent 按 `decision_rules.md` 生成优化建议清单：
- 按 category 占比排序 → 对应优化项（grounding→A3/0.1/0.3；perceptual→A2/0.8；progress→P1-1.1；recovery→P1-1.2；environment→修机器）
- 标出"回滚候选"（token 涨>50% 成功率不动）
- 标注哪些缺陷票命中"检测只说话不拔电"信号（loops>0 仍死）

**检查点 C3**：建议清单 + 缺陷票汇总发给用户，**等拍板**。agent 不得自行改 executor 代码。

---

## 5. 阶段 D —— 日常真实任务遥测（可选，低成本顺带）

agent 可定时/手动模拟发真实指令（或引导用户在 B 端发），`data\eval\runs.jsonl`
自动积累。攒 20+ 行后：
```powershell
python eval\report.py --raw runs.jsonl   # 或按 HOWTO §5 命令看分布
```

---

## 6. Agent 安全与纪律（全程）

1. **只做评测台命令，不改生产代码**：`eval/` 与 `server/tests/` 的改动需人批准；
   `calibrated:true` 是唯一允许 agent 改的数据字段（且须 C1 签收后）。
2. **不擅自扩 oracle 谓词 / 改 loader**（铁律：谓词表与 loader 变更=设计变更，走人审）。
3. **每步落日志**：命令、输出摘要、检查点结论写 `eval\calib_evidence\agent_log_<date>.md`，
   结尾附 HEAD sha。
4. 遇到确定性失败（命令非零退出）→ 记录后**停**，不盲目重试 3 次以上。
5. sidecar 用完 `stop_all.bat` 或 taskkill :8011 清理，不残留进程。
6. 改动 .bat 前过 `check_bat_parens.py`；不动红线双层、不引 :8010/OmniParser/Mock。

---

## 7. 检查点总表（agent 必须停等人工的位置）

| 检查点 | 触发 | 等待内容 |
|---|---|---|
| C0 | 环境就绪 | 确认开工 |
| C1 | 每个任务两向证据齐 / oracle 可疑 / gold selftest 后 | 签收表逐条确认 → 才置位 |
| C2 | delta 报告生成 | 回滚/合入裁决 |
| C3 | 缺陷票+优化建议 | 优化项拍板 |
