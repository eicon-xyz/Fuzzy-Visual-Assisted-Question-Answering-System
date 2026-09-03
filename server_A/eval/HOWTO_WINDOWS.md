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
