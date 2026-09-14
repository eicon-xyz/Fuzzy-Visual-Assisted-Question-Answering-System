# Windows 跑分手册（T4）—— 首次真跑与基线回测

前置：这台机器 = 评测专用时段（任务串行走完 ~2-4h/批），`server_A/server/.env` 有 key，
桌面能真实操作 UIA（锁屏会毁一批任务，关休眠）。

## 0. 一次性准备
```bat
cd /d D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System
git checkout master && git pull --ff-only origin master
```
> 注：D: 当前开发在 `front` 分支（desktop/Electron 工作）。评测请切 master 跑完再切回，
> 或用第 4 节的 worktree 方式并行。

## 1. 起 Sidecar（评测模式）
```bat
server_A\server\.venv\Scripts\python -m uvicorn server.main:app --port 8011
```
窗口保持打开。遥测默认落 `server_A\data\eval\runs.jsonl`。

## 2. 先校准，再跑分（铁律）
未校准（`tasks/seed.json` 里 `calibrated:false`）的分数只能用来修 oracle。
校准一条任务 = 在 Windows 上：
1. 人工照 instruction 做一遍 → `python eval\run_eval.py --only <id> --repeats 1 --label calib-<id>`
   看 `oracle_trace`，若 oracle 判 FAIL → 修 oracle 至 PASS；
2. 故意不做关键动作再跑一次 → 必须 FAIL；
3. 两向都过 → 把该任务 `"calibrated": true`，提交。

优先校准这 5 条（全文件/窗口标题类，最稳）：
`notepad_type_save`、`explorer_rename_file`、`explorer_new_folder`、`notepad_type_chinese`、`notepad_click_nonexistent`

## 3. 当前批次全量跑分
```bat
server_A\server\.venv\Scripts\python eval\run_eval.py --repeats 4 --label master-t3
server_A\server\.venv\Scripts\python eval\report.py eval\results\master-t3.jsonl --out eval\results\master-t3.md
```
中断可续跑（已完成实例自动跳过）。

## 4. P0 前基线回测（回答"这轮改动值多少"）
```bat
git worktree add ..\hajimi-base 049acc8a
:: 基线批（旧代码 + 新 runner——runner 与代码解耦，报告字段缺 tel 会容错）
cd /d D:\HAJIMI_B\hajimi-base
server_A\server\.venv\Scripts\python -m uvicorn server.main:app --port 8011   (新窗口)
server_A\server\.venv\Scripts\python eval\run_eval.py --repeats 4 --label base-p0pre
:: 现行批（主目录 master）
cd /d D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System
server_A\server\.venv\Scripts\python eval\report.py ..\hajimi-base\eval\results\base-p0pre.jsonl eval\results\master-t3.jsonl --out eval\results\delta-p0.md
git worktree remove ..\hajimi-base
```
注意：基线代码没有 expect/name/gate 等工具契约，同批任务在基线上会更差——这正是我们要的数字；
runner 对缺失遥测字段容错（tel=None），只有 pass/wall 可比。

## 5. 日常运行任务的量化（零成本顺带）
正常经 B 端发指令即可：每次任务自动追加一行 `data/eval/runs.jsonl`（含 token/轮次/
gate 拒收/卡死触发/expect 命中）。攒 20+ 行后：
```bat
server_A\server\.venv\Scripts\python -c "import json,collections;rows=[json.loads(l) for l in open(r'server_A\data\eval\runs.jsonl',encoding='utf-8')];print(len(rows),'tasks, ok rate:',sum(r['final_status']=='success' for r in rows)/len(rows))"
```

## 6. 判读要点（防自欺）
- **All-Pass@4 才是生产口径**；pass@1 高但 All-Pass 低 = 不稳定，别急着庆祝；
- 负向任务（expect_status:fail）过少 = agent 在乱报 done，看 gates.unverified_done；
- `loops.*` 高但任务仍失败 → P0-0.4 只会说话不会拔电，P1-1.1（清历史重规划）优先级升；
- token 均值较基线上涨 >50% 且成功率没动 → 该改动回滚候选（报告 §四 预设规则）；
- 环境类失败（environment/timeout）>10% 先修机器（锁屏/弹窗/更新），别改代码。

## 7. 扩充任务集
- 用户真实失败指令 → `tasks/*.json` 新文件（source: user-failure:<日期>），走完 §2 校准才计分；
- 从 WindowsAgentArena 移植 2-3 条作严格度锚点（其 setup/checker 语义翻译成我们的谓词表）。

## 8. Pilot 批（WAA 移植 10 条，tasks/waa_pilot.json）
`eval/waa2seed.py` 从 microsoft/WindowsAgentArena 移植的 pilot 批：7 正向 + 3 负向，
全部 `calibrated:false`、`source:"waa:<原id>"`、带 `waa_orig` 溯源快照。产物落
`%LOCALAPPDATA%\HAJIMI\eval\waa_pilot\` 沙箱（setup 建、cleanup 删，不碰真实桌面/用户目录）。
7 条正向各带 `calib_gold`（"直接落任务终态"的 PowerShell 脚本），默认走 §8.1.2 的
gold 自动校准；3 条负向无 gold 路径，走 §8.1 人工流程。校准完成后 `calibration_method`
显式区分两路（`gold-v1` / `human`）。
重生成（需外网；离线复现加 `--offline <WAA缓存目录>`）：
```bat
python eval\waa2seed.py --out eval\tasks\waa_pilot.json
```

### 8.1 逐条校准·人工路径（负向 3 条 + 无 gold 任务；铁律同 §2 两向皆过）
> **正向 7 条不必从这里开始**——先看 §8.1.2 的 gold 自动校准（机器 selftest +
> 人审 15 分钟）。本节仍是校准语义的基准：校准=证明 oracle 判据与任务真终态
> 双向一致（真做→PASS、故意失败→FAIL）；gold-v1 只是把这个双向证明机器化
> （初始 FAIL ↔ gold PASS ↔ 复位 FAIL），**不豁免人审 gold 与 instruction 的语义等价**。

以 `waa_notepad_draft_save` 为例（其余换 id 同理）：
1. **真做**：照 instruction 人工把 `This is a draft.` 存进提示的沙箱路径，然后
   `python eval\run_eval.py --only waa_notepad_draft_save --repeats 1 --label calib-draft`
   （agent 会跑同一条指令——没关系，人工已把产物摆对，oracle 判 PASS 即证明判据正确；
   看 `oracle_trace` 逐谓词输出）。判不了→修 oracle/recipes 后
   `python eval\waa2seed.py` 重生成，禁止放宽。
2. **故意做错**：删沙箱目录重跑（setup 会重建），人工不做或写错一个字符再跑一次 → 必须 FAIL。
3. 两向都过 → `python -m eval.calib <id> --calib-done` 置位（写 `calibrated: true` +
   `calibration_method: "human"`；手改 JSON 也可，但两键必须一致标注）。

#### 8.1.1 用 calib 加速（`eval/calib.py`，推荐路径）

上面每步都要手敲 run_eval + 翻 `results/*.jsonl`；校准 pilot 批用 calib 助手，
每任务压缩成三条短命令（工作目录 `server_A`，Sidecar **不需要**启动——calib 只跑
setup/判分，不碰引擎）：

```bat
:: 第 0 步（可选）：看全部任务的校准进度 / 当前该做哪条
python -m eval.calib --list
:: ① 造初始态（复用 runner 的 PS 执行器跑该任务 setup_ps1，幂等可重跑）
python -m eval.calib waa_notepad_draft_save --setup
:: ② 照 --show 人工"真做"：INSTRUCTION 段是宏展开后的真实路径，ORACLE 段逐谓词告诉你判什么
python -m eval.calib waa_notepad_draft_save --show
:: ③ 现场判分（oracle 逐谓词 trace + ORACLE: PASS/FAIL，退出码 0/1）——真做后必须 PASS
python -m eval.calib waa_notepad_draft_save --check
:: FAIL 方向：--cleanup 复位 → 再 --setup → 故意不做/做坏 → 再 --check，此时必须 FAIL
:: 两向皆过 → 置位（calibrated:true + calibration_method:"human" 同行内联写入；
:: 只动该任务一行。--check PASS 只算单向，别偷懒）
python -m eval.calib waa_notepad_draft_save --calib-done
```

- 任务 id 支持唯一前缀（`waa_calc` 即命中 `waa_calc_days_to_file`）；歧义会列出候选。
- 多 seed 任务默认用首个 seed 校准；`--seed b` 换值，`--seed all` 逐个全验。
- `--check` 判不了/判太松 → 仍按 §8.1 改 `waa2seed.py` 配方后重生成，禁止放宽
  （gold 路径同理：`--selftest` 某段翻转先修配方/环境，禁止给 gold 加豁免）。
- **坑（必须知道，§8.1.2 有更新版）**：`tasks\waa_pilot.json` 由 `waa2seed.py` 生成，
  `--calib-done` 写进去的校准位**在下次重生成时会被整体打回**。重生成后先跑
  `python -m eval.calib --list` 核对，未核对前不得拿 `calibrated` 列出数。
  正向带 gold 的任务恢复校准位已不必从零人工两向——见 §8.1.2 的重放规则。
- `--setup/--check/--cleanup/--selftest` 是评测机上的现场动作，非 Windows 会直接拒跑；
  `--list/--show/--calib-done` 在任何机器可用（写文档、看任务时用）。

#### 8.1.2 gold 自动校准（正向 7 条默认路径：机器 selftest + 人审 15 分钟）

正向任务的配方里带了一组 `calib_gold`——"直接落任务终态"的 PowerShell（文件类
=建沙箱目录+Set-Content 落产物；注册表类=reg add 写 oracle 同名同值；move/archive
类=建终态+删原位模拟「已移走」）。全部幂等、只写 `$env:EVAL_DIR` 沙箱或任务自声明的
HKCU 键、不启动 GUI、不依赖网络。机器替你跑完两向证明，人只判语义：

```bat
:: ① 机器五段（Windows）：setup → check 断言 FAIL(初始态) → 跑 calib_gold →
::    check 断言 PASS → cleanup → 复 check 断言回 FAIL(可复位、防脏状态掩盖)。
::    任一断言反 → 整体 FAIL 退出码 1 且【不写状态戳】；全过才写戳。
python -m eval.calib waa_notepad_draft_save --selftest
:: ② 人审（7 条共约 15 分钟）：--show 的 CALIB_GOLD 段逐行对照 instruction 与
::    notes 里的 gold_semantics（"gold 写了 X；人审点：instruction 说 Y，两者是否
::    等价"）。机器证的是 oracle↔gold 自洽+可复位；gold 是否任务的**正确终态**
::    是只有人能下的语义判断——跳过这步直接置位 = 自欺。
python -m eval.calib waa_notepad_draft_save --show
:: ③ 认可后置位：calibrated:true + calibration_method:"gold-v1"
python -m eval.calib waa_notepad_draft_save --calib-done --via-gold
```

**戳语义与失效规则**：`--selftest` 全过写 `%LOCALAPPDATA%\HAJIMI\eval\.calib_stamps\<task_id>.json`
（`task_hash` + `ts` + 段清单）。
`task_hash = sha256(canonical_json(oracle + calib_gold + setup_ps1 + cleanup_ps1 + instruction))`
——**配方语义任何一处变更（含重生成、手改路径/值）自动令旧戳失效**；另有 **7 天时限**，
防"半年前验过的环境"蒙混。`--calib-done --via-gold` 必须持有效戳，否则拒绝并指路先
`--selftest`。`--list` 的 method 列：`gold-v1` / `human` / `gold✓`（有有效戳但未置位）/ 空。

- **逃生舱**：`--selftest --skip-reset-check` 跳过第⑤段（cleanup+复位复 check），用于
  不想清掉本机现状的场合——会打警告并在戳的 phases 里记 `skip_reset_check`；
  复现他人判据时别用。
- **重生成丢校准位（更新版纪律）**：重生成照旧把 `calibrated`/`calibration_method` 打回。
  但正向任务恢复不再从零人工：配方内容未变（task_hash 一致、戳在 7 天内）→
  直接 `--calib-done --via-gold` 重放；配方变了 → 旧戳自动作废，重跑一次 `--selftest`
  即可再置位。重生成后仍必须先 `--list` 核对，未核对不得拿校准计数。
- **网络注意**：gold 段全部离线；唯一例外是 `waa_notepad_count_example` 的 **setup** 段
  要联网抓语料 largefile.txt——评测机离线时该条 `--selftest` 会卡在第①段，
  先联网跑通一次 setup 或临时放行网络。
- **负向 3 条不在此路**：无 calib_gold，`--selftest`/`--via-gold` 会拒；保留 §8.1 人工
  流程，置位用不带 `--via-gold` 的 `--calib-done`（写 `calibration_method:"human"`）。

建议顺序（先稳后花）：
1. `waa_settings_notifications_off`、`waa_settings_storagesense_weekly`（注册表直读，
   最稳；`--selftest` 五段全是 reg add/delete，零 GUI 零文件）
2. `waa_fe_move_myfolder`、`waa_fe_archive_docx`、`waa_notepad_draft_save`、
   `waa_calc_days_to_file`（文件副作用；archive 条素材已改 setup 本地确定性生成——
   上游 winarenafiles 的 docx 实测 0 字节占位，校准链无网络依赖）
   `waa_notepad_count_example` 放最后（setup 需联网抓语料，见上网络注意）
3. 负向 `waa_inf_vscode_arabic`、`waa_inf_vlc_autoclose`、`waa_inf_vlc_ab_replay`：
   先确认评测机装了 VS Code / VLC——没装则该条归因 `app_absent_env_infeasible`
   （仍测「不假成功」：正确出路=report_infeasible→task_failed→oracle 现场保护=true→pass；
   agent 乱点扩市集/假 done→fail）。校准 ①=什么都不做直接跑（引擎应自证不可行拿 pass）；
   ②=诱导验证：人工先把现场破坏（如把 VS Code 窗口关掉同时开一个标题含 Marketplace 的窗口）
   确认 oracle 会 FAIL——做不到时至少人工打开目标 app 停留后取消，确认 oracle_ok=true。
   各条 notes 里已标 attribution_class 与已知收紧点。

### 8.2 首轮 pilot 跑分（校准完成后）
> 口径提醒：runner 无 `--seeds` 参数——seed 维度由任务 `seeds` 字段自动展开
> （pilot 批 3 条 ×3 seeds + 7 条 ×default = 16 实例/轮），轮次用 `--repeats`。
```bat
:: Sidecar 起着（§1）。只跑 pilot 批（--only 列 10 个 id）：
server_A\server\.venv\Scripts\python eval\run_eval.py --repeats 4 --label pilot-t1 ^
  --only waa_notepad_draft_save,waa_notepad_count_example,waa_calc_days_to_file,waa_settings_notifications_off,waa_settings_storagesense_weekly,waa_fe_move_myfolder,waa_fe_archive_docx,waa_inf_vscode_arabic,waa_inf_vlc_autoclose,waa_inf_vlc_ab_replay
:: 或单目录整体跑（不混自研 20 条）：
::   mkdir eval\tasks_pilot & copy eval\tasks\waa_pilot.json eval\tasks_pilot\
::   python eval\run_eval.py --tasks eval\tasks_pilot --repeats 4 --label pilot-t1
:: 与自研集合跑（--tasks 默认指 eval\tasks，30 条一起）：
::   python eval\run_eval.py --repeats 4 --label full-t1
server_A\server\.venv\Scripts\python eval\report.py eval\results\pilot-t1.jsonl --out eval\results\pilot-t1.md
```
report 出数即含逐任务 All-Pass@4、pass@1、成本与四类失败打标；未校准条目分数照旧
只用于修 oracle，不进汇报口径。
