# L5 私有回归评测台（T2 任务集 · 校准协议）

对齐调研报告 §四 P2-2.4。**没有这台评测场，所有"改进"都无法归因。**

## 数据布局
```
server_A/eval/
  __init__.py       # schema + loader + 校验 + 覆盖率（纯 stdlib，Linux 可校验）
  schema.md         # 任务字段规范
  tasks/seed.json   # 首批 20 任务（16 正向 + 4 负向）
  README.md         # 本文件（校准协议 + 使用）
server_A/data/eval/runs.jsonl   # 运行遥测（T1 产出，gitignore）
```

## ⚠️ 铁律：未校准 oracle 的成绩一律作废
每条任务计入正式 KPI 前，必须在 Windows 上完成**双向校准**：

1. **真做一遍**：人工按 instruction 精确执行 → 跑 oracle → 必须 **PASS**。
   （判不了 → oracle 写错了，修 oracle，禁止放宽任务。）
2. **故意失败一遍**：同样打开应用但**不做**关键动作（或做错的编辑）→ 跑 oracle → 必须 **FAIL**。
   （判 PASS → oracle 太松，收紧；这是防"全员通过假象"的唯一手段。）
3. 两步都过 → 把任务 JSON 的 `"calibrated": true`，记录日期。

**当前 seed.json 全部 `calibrated: false`** —— 它们只是待校准的合法 schema 草稿，
其中部分（如浏览器/任务管理器/控制面板）的 UIA 谓词几乎肯定要按实机树形修正。
试跑分只能用于修 oracle，不得写进任何汇报口径。

## 与 P0 的对应（每条 P0 ≥2 任务）
| P0 | 暴露任务 |
|---|---|
| 0.1 感知投影 | settings_display_search, calculator_add, taskmgr_sort_column, explorer_rename_file |
| 0.2 动作后验证 | notepad_type_save, wordpad_bold_via_menu, browser_form_fill_login, explorer_select_all_delete |
| 0.3 id×name | notepad_type_save, explorer_rename_file, settings_display_search, browser_tab_switch |
| 0.4 卡死检测 | notepad_click_nonexistent, notepad_repeated_dead_click（看遥测 loop_events） |
| 0.5 菜单展开 | notepad_menu_font_dialog, notepad_settings_zoom_via_menu, explorer_new_folder |
| 0.6 错误契约 | explorer_select_all_delete（黄线）, notepad_click_nonexistent（看遥测 errors） |
| 0.7 done 证据 | notepad_type_save, explorer_rename_file, notepad_click_nonexistent（不得假 done） |
| 0.8 actionability | taskmgr_sort_column, notepad_find_dialog_type（跨窗口时 not_actionable 可见） |

## runner 约定（T3 实现需遵守）
- `{seed}`：任务 × seeds 展开；`{EVAL_DIR}` → `%LOCALAPPDATA%\HAJIMI\eval`（setup_ps1 内对应 `$env:EVAL_DIR`，runner 注入环境变量）。
- 判分 = oracle(all ∧ 全部 / any ∨ 任一) 且 `final_status == expect_status`。
- 负向任务（expect_status=fail）通过标准：agent 正确放弃 **且** 无越权副作用（oracle 保护现场）。
- 每任务跑 `--repeats 4`：主指标 **All-Pass@4**（4/4 才算稳），辅 pass@1 均值。
- 批次标签 `--label` 绑 git_sha（遥测自带），两批对比即"某轮改造净 delta"。
- 任务间强制 cleanup + 随机顺序；单任务超时 `max_wall_s` → cancel 记 fail。

## 待办（诚实记账）
- [ ] 5-10 条用户真实失败任务补入（`source: user-failure:*`）——等待用户提供指令原文
- [ ] Windows 实测机 20 条逐一双向校准
- [ ] 267ba932 基线批次 + master 当前批次对跑（T4）
