# HAJIMI L5 执行引擎架构对标开源调研报告

> 调研日期：2026-09-02 · 作者：HAJIMI 工程 · 状态：v2（A/B/C/D 四组全部汇入；B 组为检索直证初稿，若后续补充仅增量修订）
> 目的：HAJIMI L5（UIA 自动执行）在**复杂多步任务**上成功率低，对标开源桌面/GUI/浏览器 Agent 的架构设计，产出可落地的改造路线。
> 结论速览：**瓶颈不在"模型不够聪明"，而在 agent 骨架的四个缺件——感知被截扁、动作后零验证、偏航无账本、经验不可回放。** 四项全部可用现有 deepseek-chat + UIA 落地，不需新模型；「模型不动、只换骨架」的对照实验收益（+3×/-31%/3.8→12.5）远大于换模型的边际。

---

## 一、现状体检（基于 server_A 源码逐行核对）

### 1.1 执行链全景

```
用户指令
  → planning/router.process_query → planning/planner.plan_steps(query)   【一次性静态分解，纯文本 deepseek-chat】
  → executor/engine.run_plan_agent_loop(task_id, goal, steps)            【for 循环逐步执行】
      每步 → executor/agent.ExecutionAgent.execute_step()
              循环 ≤50 轮：LLM function-calling → dispatch_tool → 结果回灌
      失败 → 同指令重试 ≤1 次 → 仍失败 → 整个任务 task_failed（break）
  → SSE 事件流 → B 端时间线
```

### 1.2 已经做对的（保留）

| 机制 | 位置 | 评价 |
|---|---|---|
| UIA 控件绑定优先（Invoke/Select/Toggle/SetValue），坐标只做回退 | `uia_bridge.act()` | 方向与业界一致（Instructor/UFO 同款），这是 HAJIMI 最大的资产 |
| element_id 而非坐标暴露给 LLM（动作参数语义化） | `agent.py` 工具面 | 正确的 ACI（agent-computer interface）设计 |
| 双层红线（B端归一化 + Sidecar redline/safety） | `safety.py` | 超出多数开源 demo 的安全工程 |
| 连续 3 次 get_screen_info 的复读警告、截图重叠检测 | `_do_get_screen_info` | 简易 loop-detection 雏形 |
| 成功/失败轨迹后台抽取 + system prompt 注入 | `memory/extractor+retriever` | 有骨架，产物太弱（见 §1.3-6） |
| 浏览器 DOM 通道（snapshot/CSS selector）与 UIA 双轨 | `browser_*` 工具 | 网页侧准确率明显好于桌面侧——这本身就是对照组 |

### 1.3 与准确率直接相关的六个断点（全部源码实证）

1. **感知被截扁：控件树 → 平面 id+content 列表**
   - `uia_bridge._walk`：`_MAX_DEPTH=5 / _MAX_NODES=60` 深度广度双截断；
   - `_do_get_screen_info` 返回给 LLM 的只有 `{"id","content"}`×前 **30** 个；**control_type、IsEnabled、可用 Patterns、bbox、窗口/层级归属全部丢弃**；
   - prompt 里写的"利用 left_ids/right_ids 空间关系定位"是**死条款**：UIA 路径 spatial 永远空列表、OmniParser 路径 `compute_spatial=False`；
   - 后果：深层嵌套/同名多控件（"确定"按钮×3）时 LLM 只能瞎猜；`confidence=0.9` 是硬编码假值。

2. **动作后验证根本没接线**
   - `uia_bridge.verify()`（IsEnabled/IsOffscreen 轮询）写得完整，但 **agent.py 全文无任何调用点**；
   - 动作→结果之间只有 `time.sleep`；完成判定 = 执行 LLM **自评** `mark_step_done`，无独立校验者；
   - 后果：假 done 沿 previous_steps 传染后续所有步骤——"中途偏航不可恢复"的第一来源。

3. **有 Replan 之名、无 Replan 之实**
   - `engine.py` docstring 写着 `Plan → … → Next/Replan`，代码里 **for 循环静态走完预规划 steps**，步骤失败仅同指令盲重试 1 次，随后整个任务终止；
   - `planning/replanner.py` 存在但服务于旧 L4 元素绑定，未接入执行回路；
   - 后果：计划是开局一锤子买卖，UI 实际状态与计划的任何偏差都无法修正。

4. **上下文管理原始**
   - messages 线性增胖（50 轮 × 工具结果 JSON 全量保留），无压缩、无滑动摘要；`max_tokens=512` 又限制思考长度；
   - 每轮固定 nudge「继续。你还可以调用工具」，无结构化 Thought/Progress 记录；
   - 后果：长步骤后期模型"忘了"目标约束，行为漂移。

5. **动作空间缺口导致结构性失败**
   - 无 `wait_for(条件)`（Playwright auto-waiting 哲学缺席，全凭 wait(2) 猜时间）；无 right_click/drag/hover；**ExpandCollapse pattern 探测了却没用进 `act()`**（菜单/下拉只能坐标点击，展开后无新快照协调）；无窗口级动作（SetFocus/最小化/多窗口切换）——但 UIA 都有原生支持；
   - `get_screen_info` 前全局 `pyautogui.press("esc")` 副作用危险（会关掉刚打开的菜单）。

6. **经验记忆不可回放**
   - `memory/extractor` 产物 = `{app, path, summary}` 事实三元组，检索后以文本注入 prompt；
   - 缺少 AWM/Voyager 式的**可执行工作流沉淀**（参数化步骤序列 + 成功率统计 + 直接回放执行），"做过一次"不能变成"下次做得更快更准"。

### 1.4 与业界公开失败归因的对照（数字详见 §2.4①）

OSWorld / WindowsAgentArena / AndroidWorld / WebArena 的 error analysis 把失败拆成：**grounding（找错/找不到）、perceptual（看不见关键状态）、planning/progress-perception（不知道自己卡住）、recovery（错了不自救/提前放弃）**。量化锚点：OSWorld 550 失败样本 **>75% 含点击不准**；WebArena **54.9% 可行任务被误判"不可行"提前放弃**；RoTS 证明**从错误状态续跑成功率随错误深度暴跌 41–75%**；UFO² **62% 失败源于控件检测盲区**。

对照 HAJIMI：§1.3-1/5 对应 grounding+perceptual（但我们的"grounding"是选错控件而非算错坐标——UIA 语义桥已比像素路线占先，截扁感知把优势丢了）；§1.3-3/4 对应 planning/progress-perception（Magentic 去账本 -31% 同型）；§1.3-2/6 对应 recovery+泛化。**问题分布与业界完全同构，且断点 1、2、3 是"能力写了没接线"的纯工程问题，不是 deepseek-chat 的能力上限**——WebArena 的教训尤其提醒我们：我们的 `mark_step_failed` 过早触发同样可能造成"本可行却放弃"。

---

## 二、开源项目架构横评

> 四路并行调研：A=Windows/UIA 系 ✅、B=GUI 模型与框架 ✅（直证初稿）、C=Loop 编排骨架 ✅、D=可靠性工程与失败归因 ✅。
> A/C/D 三组含源码级证据（直读仓库 main 分支/论文原文，非二手转述）；原始抓取快照存 `/tmp/research/`、`/tmp/ufo_src/` 可复核。所有数字标注出处。

### 2.1 A 组：Windows / UIA 系桌面 Agent（与 HAJIMI 栈同构，抄得动）

#### ① Microsoft UFO / UFO² / UFO³（[microsoft/UFO](https://github.com/microsoft/UFO)，9.6k★，持续活跃）——最重要对标对象

- **Dual-agent 分工**：HostAgent 管 WHAT/WHEN（选应用、全局计划、AppAgent 生命周期、子窗口切换），AppAgent 管 HOW/WHERE（控件选择与动作），两侧各是一个 **7 态 FSM**（CONTINUE/SCREENSHOT/FINISH/FAIL/ERROR/PENDING/CONFIRM），Status 驱动状态迁移——失败不是"重试或死"，而是**分级降级**：FAIL 交回 Host 换策略、ERROR 终止本 round、PENDING 问用户、CONFIRM 敏感动作求确认（[UFO² overview](https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/overview.md)，v1 论文 [arXiv:2402.07939](https://arxiv.org/abs/2402.07939)）。
- **控件序列化（对§1.3-1 的直接答案）**：不做嵌套全树 dump，而是「两级过滤 + 平面编号」——硬过滤=10 种高价值 ControlType 白名单（Button/Edit/TabItem/Document/ListItem/MenuItem/TreeItem/ComboBox/Hyperlink/ScrollBar）；软过滤=从 plan 抽关键词→embedding 余弦 top-k（`control_filter.py`）；投影字段 `control_type/control_id/control_class/control_name/control_text/control_rect/selected/source`（`inspector.py:637`）；**动作后预期界面变化的动作强制返回 SCREENSHOT 态重标注小集合**——LLM 主视图永远是"过滤后的扁平编号列表+SoM 标注图"。
- **动作前置校验（防幻觉点击）**：①`_verify_id`——动作参数强制同时报 `id+name`，服务端核对不符即警告并回报真名；②UFO² **投机批量执行**：一次 LLM 调用产出 k 个动作，逐个用 UIA `is_enabled/is_visible` 校验后顺序执行，失败即早停、报 partial、触发重规划（[UFO² 论文 §3.6, arXiv:2504.14603](https://arxiv.org/abs/2504.14603)，称 **LLM 调用降 51%**）。
- **API 优先、GUI 兜底**：同一 Command Dispatcher 路由 UIA 动作与 Excel COM/Word/PPT/pdf/cli 原生 API（[hybrid_actions 文档](https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/core_features/hybrid_actions.md)；佐证：[API Agents vs. GUI Agents, arXiv:2501.05446](https://arxiv.org/abs/2501.05446)——API 可用场景成功率高 **15–30%**）。
- **每步滚动重规划**：全局/局部双层计划，每步显式修订，"不必严格遵循旧计划"（v1 论文 §3.5.4）；子任务完成写 `result` 回执供下游决策。
- **经验学习**：官方帮助文档 RAG + 成功轨迹总结为 few-shot（`record_processor/`、[experience_learning 文档](https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/core_features/knowledge_substrate/experience_learning.md)）；事后 **EvaluationAgent 按 CoT 子目标逐项打分**（[evaluation_agent](https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/evaluation/evaluation_agent.md)）。
- **扎心数据（校准我们的优先级）**：UFO² 论文错误分析——GPT-4o 版在 WindowsAgentArena 上 **62% 失败归于 Control Detection Failures**（第三方/自绘 UI 的 UIA 覆盖盲区），因此 UFO 才做 UIA+OmniParser IoU 混合检测。⇒ 纯 UIA 有约 1/3 结构性盲区，但那是"UIA 已覆盖部分先把工程做对"之后的二期问题。
- **HAJIMI 技术栈被官方背书**：UFO 仓库自带 `prompts/examples/nonvisual/`（纯文本无截图模式）与 `ufo/llm/deepseek.py`——"文本 LLM + UIA"是受支持路线。

#### ② Windows-MCP / Windows-Use / uiacli —— "AX-first 双通道 + WaitFor + 熔断"三件套

> 注：原任务单里的 `instructor-gui`/`Ontoterm` 经查 GitHub **不存在**；该意图的真实载体是下述 UIA 工具化项目族（[567-labs/instructor](https://github.com/567-labs/instructor) 是 Pydantic 结构化输出库，恰好可用于强约束 deepseek 的动作 JSON——UFO 就是这么用的）。

- **[CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP)**（6.9k★，官方明言"不依赖 CV 模型"）：观察两档 `Screenshot`(省 token)/`Snapshot`(完整 UIA 树+交互元素 id+可滚动区域)；**`WaitFor`：在一次工具调用内轮询"文本/窗口/元素/焦点出现"= 动作后置条件断言**；`MultiEdit/MultiSelect` 批量 label→坐标；`region` 局部裁剪省 token；DOM 模式专取网页。
- **[CursorTouch/Windows-Use](https://github.com/Jeomon/Windows-Use)**：默认 UIA 读屏、`max_steps=25` + **`max_consecutive_failures=3` 连续失败熔断**；`wait_tool`（等渲染稳定）、`memory_tool`（跨步 markdown 笔记）、`multi_edit_tool`（一次填整表单）。
- **[amitse/uiacli](https://github.com/amitse/uiacli)**（"Windows 版 browser-use"）：`uia tree --depth 2` 浅探测按需下钻；**hybrid input：UIA patterns 优先、SendInput 兜底**；所有响应结构化 `{ok, error.code, error.message, error.hint}`——**错误自带 hint 回灌 LLM 自纠**（最小可用的失败恢复接口）；README 记录 14 条 UIA 实操坑（UWP 树稀疏、SetCursorPos 不触发事件等，HAJIMI 排障可直接对照）。
- **[eric-patton/cwin](https://github.com/eric-patton/cwin)**：PostMessage→UIA→SendInput 三层输入栈按 app 框架自动选通道、不抢焦点——我们"每窗口动作/后台执行"的参考实现。

#### ③ Anthropic Computer Use（工程契约层可全抄，视觉层不可）

- demo 的 [loop.py 刻意做薄](https://github.com/anthropics/claude-quickstarts/tree/main/computer-use-demo)（388 行）：契约=每个 tool_result 带 `is_error` + 新截图；**同回合多动作顺序执行、首败即停**（后续返回 "Not executed: earlier action failed"——防止在失效假设上继续操作，正对应"偏航不放大"）。
- [官方 best-practices（2026-05）](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude)中**纯文本 LLM 同样成立**的四件：① **≥20 步任务强制外置 `TODO.md`**，做完勾选、迷路时"重读 TODO.md"（任务状态搬出上下文窗口）；② **8 段式 compaction 模板**（USER INSTRUCTIONS 逐字保留 / CONSTRAINTS / ACTIONS TAKEN / **ERRORS AND FIXES(已试败方案防重蹈)** / PROGRESS / CURRENT STATE / NEXT STEP）；③ 重试分级（API 指数退避 / 空回复重试 / max_iters 上限 / 中断注入伪 tool_result 保持消息合法）；④ **宣布完成前先落盘结果+终态证据**（durable result）。
- VLM 专属（暂不适用）：截图预缩放到 1280×720 的坐标系对齐、`zoom` 局部工具、`computer_batch` 批量动作+批次末尾验证截图、视觉 advisor 双模型分层（执行 Sonnet、规划/纠偏 Opus）。

#### ④ 评测与基准（HAJIMI 建回归集的现成模板）

- **[WindowsAgentArena](https://github.com/microsoft/WindowsAgentArena)**（NeurIPS'24，[arXiv:2409.08264](https://arxiv.org/abs/2409.08264)）：任务自带**配置化初始状态断言 + 成功判据**（env-check oracle，不靠 LLM 自评）；`--som-origin` 可切 `oss`(GroundingDINO+OCR)/`a11y(uia|win32)`/`mixed`——正好量化"UIA 感知 vs 视觉感知"对我们任务的覆盖差。
- **[COLA, arXiv:2503.09263](https://arxiv.org/abs/2503.09263)**：需求→原子能力单元→agent 池路由；**交互式回溯**（人可触发 state rollback 做非破坏性过程修复）。
- **[microsoft/cua_skill](https://github.com/microsoft/cua_skill)**（新）："Computer Use Agent with Skills"——操作沉淀为可复用 skill 的微软官方实验，验证 §1.3-6 方向。

### 2.2 C 组：Loop 编排骨架（browser-use / Magentic-One / OpenHands / Skyvern / LangGraph）

#### ① Magentic-One「双账本」—— 对"偏航不可恢复"最对症，纯文本机制

- 内循环每轮 Orchestrator 必答固定 JSON：`is_request_satisfied / is_in_loop / is_progress_being_made / next_speaker / instruction_or_question`，每项 `{reason, answer}`——**先写理由再下结论**，schema 强校验。
- 振荡检测实证（活代码在 [microsoft/agent-framework](https://github.com/microsoft/agent-framework) `_workflows/_magentic.py`，原 magentic-one 仓库已 404）：`无进展 或 in_loop → stall_count+=1`；有进展 `max(0, stall_count-1)` 迟滞衰减；**`stall_count>3 → _reset_and_replan()`：清对话历史、保留账本 → replan prompt 强制"先述 root cause，新计划特别避免重蹈覆辙" → 重入外循环**；外循环封顶后升级。
- 量化：消融把 Orchestrator 降级为 AutoGen GroupChat（只选说话人、无账本）**掉 31%**（[arXiv:2411.04468](https://arxiv.org/abs/2411.04468)）。
- HAJIMI 降维实现：单 agent 化简版 = 每步 +1 次 5 字段小 JSON 自评 + engine 里 stall 计数器 + 触阈值"清消息历史（留账本）→ 强制重规划"。

#### ② browser-use —— 与 L5 同构度最高，多数机制可"抄参数"

- **动作 schema 强约束**：每轮 AgentOutput 四字段必填（`evaluation_previous_goal / memory / next_goal / action`），action 只能从注册表固定 schema 选、元素按 DOM 索引引用；空动作→澄清重采样→再失败注入 noop done。
- **Loop detection（~百行纯代码可平移进 agent.py）**：动作哈希滑窗（window=20，重复 5/8/12 三级）+ **页面指纹停滞**（url+元素数+DOM 文本 sha256 连续 ≥5 步不变）→ 分级 nudge（只提醒不阻断）；连续失败 ≥3 → "REPLAN SUGGESTED + 输出新 plan_update"；max_failures=5 后追加一次"总结成果"恢复调用。
- **历史压缩**：每步压成 `<step N>`；**40k 字符触发** LLM 把旧历史+既有摘要增量重写 `<compacted_memory>`，keep_last_items=6。
- **收尾自检**：任务后独立 judge LLM 按「目标满足/轨迹质量/工具失败率」复核。
- 数据：官方 [WebVoyager 586 任务 89.1%](https://browser-use.com/posts/sota-technical-report)（对比纯截图基线 ~59%）；但 [WebSight(arXiv:2508.16987)](https://arxiv.org/abs/2508.16987) 证明真实站点 DOM/AX 树常残缺 → **结构主通道 + 像素兜底**，非结构万能（HAJIMI 的 UIA+坐标双轨方向正确，WebSight 与 UFO² 的 62% 数据互为镜像）。

#### ③ OpenHands —— 规则化卡死检测+回滚，零 LLM 成本

- `stuck.py` 五规则：4×同动作同观测 / 3×同动作皆 Error / 3×近似独白 / 异动作同观测模式(≥6) / 上下文超限循环(≥10)，比较忽略 pid 噪声；命中→ **回滚到 loop_start_idx 重跑** / 带新指令重启 / 停止。
- Action/Observation **append-only 事件流可 replay** + 显式 AgentState FSM（RESUMABLE_STATES 白名单）；condenser 策略族（LLMSummarizing 滚动摘要 / ObservationMasking 只截巨型观测 / Pipeline 组合）；microagents=关键词 trigger 命中才注入专题手册（"各软件操作手册按需加载"）。

#### ④ Skyvern —— 层级重试 + 确定性重放（搬 schema，不搬引擎）

- 三级重试：step 级 max_retries_per_step=3（重新定位）→ block 级整块重跑（**anti-bot 命中跳过重试**）→ workflow 级 continue_on_failure；失败分诊：业务失败**不重试直接 fail**（error_code_mapping）。
- block 把语义判据交给模型但字段固定：`complete_criterion / terminate_criterion / data_schema`——正面补 §1.3-2（done 无判据）。
- self-heal：确定性 CodeBlock 重放失败 → 同会话跑**目标收窄到失败步的 bounded mini-run**，修不好 fail-closed——"确定性重放为主、LLM 兜底"与 HAJIMI 双执行面同构（也为 P2 工作流回放探路）。

#### ⑤ LangGraph：现阶段不建议引入（作参照高、作依赖中低）

checkpoint/time-travel/interrupt 的本质=状态外置+每步落盘+可回滚；L5 用「step 列表+自研轻量 FSM」可拿 80% 收益，durable 多租户对单机 Sidecar 无用，画图与开放式操作冲突。

#### ⑥ 反面证据：别给 L5 加"多 agent 天团"

- [MAST（NeurIPS'25，7 框架 200+ 轨迹）](https://arxiv.org/abs/2503.13657)：14 失败模式三大类=规格 41.8% / **agent 间错位 36.9%** / 验证缺失 21.3%；最优干预仅 +15.6%。
- [Cognition《Don't Build Multi-Agents》](https://cognition.ai/blog/dont-build-multi-agents)、[Anthropic building effective agents](https://www.anthropic.com/engineering/building-effective-agents)（最简优先）、CrewAI 生产端自己用确定性 Flows 取代自主 Crews。
- ⇒ planner/critic 的价值应**降维为同循环内的账本字段、judge 调用、规则检测**，而非新增 agent。

### 2.3 B 组：GUI 模型与框架——「模型贡献 vs 骨架贡献」定量分离（初稿，B 代理终稿回来后合并校准）

> 本组关键用途：回答"复杂任务差，该怪 deepseek-chat 还是怪骨架？"——学界恰好做了把模型固定换骨架、把骨架固定换模型的对照实验。

- **Agent-S（[arXiv:2410.08164](https://www.sciencestack.ai/paper/2410.08164v1)，[simular-ai/Agent-S](https://github.com/simular-ai/Agent-S)，现演进 Agent-S2/S3）**：模型不变（GPT-4o），仅加"**经验增强分层规划**"（Manager 语义子目标 + Worker 执行 + **从成功轨迹离线归纳 workflow 存入 Reasoning Memory，在线 top-k 检索复用**）→ OSWorld 成功率 ~31%，官方称相对此前 SoTA **约 3×**。⇒ 纯骨架+经验库贡献，模型零改动。**这直接是 §1.3-6（经验不可回放）与 §四 2.1 的最强背书**；AWM 的 +51.1%（§2.4④）是同一机制在 web 域的镜像。
- **UI-TARS / UI-TARS-2（[arXiv:2501.12326](https://ar5iv.labs.arxiv.org/html/2501.12326) / [arXiv:2509.02544](https://ar5iv.labs.arxiv.org/html/2509.02544)）**：端到端原生 GUI 模型路线（感知/grounding/规划全内化于 VLM）。两点与 HAJIMI 相关：① 论文自省"真实部署中 agent 常因**缺乏自我反思**而卡死"→ 其训练数据专门合成反思轨迹——**反思/重规划是被模型厂当作一等能力训练的**，我们没训练条件，就必须用账本+熔断在 scaffold 层补（§2.2①/③）；② UI-TARS-2 把架构拆成"推理模块 + 解耦的视觉 grounding 模块 + 异步 RL + 统一动作空间"——**即使端到端模型，也在把 grounding 独立成可替换模块**，与"UIA 主 + 视觉兜底"双通道同构。其 scaffold 的"思考-规划-行动-**反思上一步是否生效**"四段式可在纯文本层复刻（反思改读 UIA diff 而非截图）。
- **Mobile-Agent-v2（[arXiv:2406.01014](https://ar5iv.labs.arxiv.org/html/2406.01014)）**：四 agent 分工（Planning/Decision/**Reflection**/Memory），**Reflection 用前后截图对比检查"操作是否真生效"，不生效则重试**——消融显示该模块是导航成功率主要贡献之一。HAJIMI 平价替代：Reflection 读 **UIA 属性 diff**（§四 0.2/0.8 的 before/after diff），不需要 VLM，成本更低。注意其论文也自认"即使有感知模块仍会出非预期操作"——**反思模块是减损不是保险**。
- **UGround（[arXiv:2410.05243](https://osu-nlp-group.github.io/UGround/)，"Navigating the Digital World as Humans Do"）**+ **OS-Atlas（[arXiv:2410.23218](https://arxiv.org/abs/2410.23218)）**：纯视觉 grounding 组件族（ScreenSpot 基准上像素定位显著优于依赖结构树的传统 agent，二者都主张"通用可插拔 grounding"）。**解读要平衡**：其结论成立于"结构树残缺的界面"；这与 D 组 Minitap 100%（结构+验证路线）、WAA 的 a11y 模式数据一起构成完整图景——**结构树信息充足时语义路由更准更省，结构盲区（UWP/自绘/网页画布）才需要视觉 grounding**。HAJIMI 正确姿势：把视觉 grounding 做成 element_id 体系的**数据源之一**（§四 2.3），而不是推翻 UIA 主通道。WebSight(2508.16987) 的反向证据已在 §2.2② 引用，两面对照。

**小结（模型 vs 骨架的归因）**：Agent-S（换骨架 +3×）、Minitap（换骨架 80.2%→100%）、Magentic 消融（去账本 -31%）、SWE-agent（换接口 3.8→12.5%）四个实验里模型都没动；而 HAJIMI 连"模型上限"都还没触到——UIA 语义桥给足了结构化信息，deepseek-chat 的规划/写码能力被 §1.3 断点白白浪费。**结论：先把 P0/P1 工程件做完，再评估是否需要 VLM/grounding 投入。**

### 2.4 D 组：可靠性工程、失败量化归因与技能库（一手来源：论文原文/官方 README，快照存 /tmp/research/）

#### ① 失败模式量化——"复杂任务准确率低"是可以分解的

- **[OSWorld](https://arxiv.org/abs/2404.07972)**：最佳 **12.24%** vs 人类 72.36%。§5.4 误差分析：550 个失败样本中 **>75% 存在鼠标点击不准**——且多为"代码注释里规划了正确步骤但坐标算错"（强规划、弱执行）。派生错误链：误点→弹窗/错窗（环境噪声）→无状态校验→无法回退→重复点击耗尽步数。
- **[WindowsAgentArena](https://arxiv.org/abs/2409.08264)**：最佳 **19.5%** vs 人类 74.5%。**文本/语义主导界面（浏览器、系统设置）显著好于图标/快捷键主导（Office、Utils）**；多模态输入比纯文本输入明显提升 → HAJIMI 纯文本+UIA 是"语义充足界面"下的合理配置，前提是快照给足语义（呼应 0.1）。
- **[AndroidWorld](https://arxiv.org/abs/2405.14573)**（M3A 30.6%）四分法：**Grounding / Perceptual（看不见关键状态）/ Reasoning（误判当前状态且不可恢复）/ Missing knowledge**——与 HAJIMI 断点几乎一一对应（①/①+②/③/缺 app 先验）。
- **[WebArena](https://arxiv.org/abs/2307.13854)** 三个刺眼数字：**54.9% 的可行任务被 GPT-4 误判"不可行"而过早放弃**（头号失败模式=提前躺平）；61 任务模板仅 4 个 100%（同模板换参数就废=没泛化，靠背题）；Observation Bias（抓到第一个疑似信息就不再验证→死循环反复 type）。
- **[OSWorld 2.0（长程）](https://ar5iv.labs.arxiv.org/html/2606.29537)**：Implicit-state 14–18.6%、Visual-spatial 8.9–13.3%；**Task 052 证明"截图→思考→点击"离散循环有结构性缺陷**（弹窗移动，观测坐标在执行时刻已失效，"再多推理也无法补偿"）→ 直接支持 HAJIMI「UIA 语义动作优先、坐标仅回退」路线。
- **GUI-RobustEval/RoTS（ICML'26 Spotlight，[arXiv:2605.29447](https://arxiv.org/abs/2605.29447)，[代码](https://github.com/AlibabaResearch/RoTS)）**：从 12 个 SOTA agent 的 1.5k 真实失败轨迹归纳 11 类自致错误——① **从错误状态续跑，成功率随错误深度单调暴跌**（−41%~−53%，恢复能力是普遍缺失维度）；② 真实失败主要是**组合式规划错误与"进度感知"错误**而非低层点击错（=我们 engine 的病）；③ 提出 **All-Pass@4** 生产可靠性指标：单次 42.9% 的模型 All-Pass@4 只有 15.5–33.8%——**单次成功率÷稳定性就是生产可用率的真实折扣**，HAJIMI 验收口径应学这个。
- 官方自认：OpenAI Operator 系统卡把"模型误执行与用户意图不符的动作"列首要危害；Anthropic 从 beta 到 2026 Cowork 一贯"先确认、可打断、会犯错"（[operator-system-card](https://openai.com/index/operator-system-card/) · [claude.com/blog](https://claude.com/blog/dispatch-and-computer-use)）。

#### ② Harness 即变量：cua 与 SWE-agent 的证据

- **[trycua/cua](https://github.com/trycua/cua)**：官方陈述"同一 agent，**Win11 上 90% 可能到 WinXP 环境 9%**"——跨 harness/环境数字不可比；三大设计：**沙箱（VM/LXC）+ 并行评测（--max-parallel）+ oracle validation（评 agent 前先验"环境+判分器"本身可解）**，把评测质量问题从 agent 能力中剥离。
- **[SWE-agent ACI（arXiv:2405.15793）](https://arxiv.org/abs/2405.15793)**：模型不变、仅重新设计"给 agent 的界面"（窗口化查看、编辑必过 linter），pass@1 从 ~3.8% 到当时 SOTA 12.5%——**接口设计的杠杆 ≥ 换模型**。⇒ HAJIMI 结论：0.1/0.2/0.6 这类"给模型更好的观察与错误反馈"就是 ACI 工程。
- 建议：**给 L5 建私有回归基准**（30-50 个真实失败任务 + UIA 属性/文件/DB 判分 oracle + VM 快照环境），否则任何改进无法归因（§四 2.4 项）。

#### ③ CodeAct / computer-api：「动作即代码」是 HAJIMI 弱项的绕道

- **[CodeAct（arXiv:2402.01030, ICML'24）](https://arxiv.org/abs/2402.01030)**：动作统一为可执行 Python（替代离散 JSON），17 个 LLM 评测**最高 +20% 成功率**——控制流、组合、报错即反馈。deepseek-chat 写代码的能力 > 精确点击的能力，**恰好绕开 L5 短板**。
- **[Open Interpreter](https://github.com/OpenInterpreter/open-interpreter)**：code-first capability 路线佐证；边界：OSWorld 2.0 的 FreeCAD 案例 agent 自主写脚本 202 步仍 partial 0.35——**代码解决表达力，不解决验证与感知**，必须配 expect。
- 落地形态（HAJIMI 版）：新工具 `run_ui_script(dry_run)`——LLM 生成受限 pywinauto/UIA 脚本（白名单 API），先 **dry-run 枚举**"将操作 N 个元素"清单→过红线→逐步执行且每步带 expect；失败回退现有逐步循环。

#### ④ 技能库/工作记忆：从成功轨迹蒸馏"宏"（有数字）

- **[AWM（arXiv:2409.07429）](https://arxiv.org/abs/2409.07429)**：自动从轨迹归纳可复用 workflow（自然语言伪码宏）选择性注入——**Mind2Web 相对 +24.6%、WebArena 相对 +51.1%，且成功任务步数下降**；在线归纳模式跨站泛化稳健。⇒ §1.3-6 的对症药，免训练。
- **[Voyager（arXiv:2305.16291）](https://arxiv.org/abs/2305.16291)**：技能库=可执行代码+embedding 检索（独特物品 3.3×、里程碑解锁 15.3×）——HAJIMI 已有 embedder/retriever，缺的正是"可执行"形态。
- **[ExpeL（arXiv:2308.10144）](https://arxiv.org/abs/2308.10144)**：不动权重、自然语言 insight 召回；**RoTS 的反面校准：10 万条人工反思样本仅 +0.6，10 万条来自自身真实错误分布的样本 +5.3，且反思占比 >0.2 会"过度修复不存在的错误"**——经验库必须蒸馏自家轨迹。
- Windows 落地：workflow JSON 模板 `{name, when_to_use, params, steps[{tool, semantic_target(UIA 非坐标), expect, on_fail}]}`，回放失败→self-heal mini-run→回炉修模板；红线层只放行白名单动作、`irreversible` 步强制确认（与 Skyvern self-heal、UFO experience、microsoft/cua_skill 同向）。

#### ⑤ expect/验证闭环：Playwright actionability 的桌面翻译

- **[Playwright auto-waiting](https://playwright.dev/docs/actionability)** 六谓词——**唯一解析、Visible、Stable(动画停)、Receives Events(不被遮挡)、Enabled、Editable**——可逐条映射 UIA：`IsOffscreen/IsEnabled/ClickablePoint/bbox N ms 不变`。这就是 §1.3-5 缺的 `wait_for` 的答案：等待条件而非等待时间。
- 业界同构件：**V-Droid** pre-execution verification→AndroidWorld 59.5%；**UFO²** AppAgent 报完成→HostAgent 验证后才推进；**browser-use** watchdog 校验动作副作用；**Minitap** 把验证做成系统组件后 100%；tinyfish 综述一句话："点了 Submit 出现确认页 ≠ 任务正确完成"。
- HAJIMI 化：每个动作工具加 `expect` 参数并返回 `{action_ok, state_changed, before/after prop-diff}`——**动作 API 永不返回裸"成功"**；`mark_step_done` 必须携带证据（UIA diff/文件 stat），无证据直接拒收（同时治 WebArena 的"过早放弃"与"虚假完成"两极）。

#### ⑥ 规划/执行分层的产品级证据 + 分级确认

- **Minitap（mobile-use，[arXiv:2602.07787](https://ar5iv.labs.arxiv.org/html/2602.07787)）**：Cortex+Planner+轻量 Executor+验证组件的分解架构**首个 100% 解决 AndroidWorld 116 任务（超人类 80%）**；消融：降档 Planner→57.8%、去验证→崩——**"当前模型 + 合适的系统设计"即达生产级**；deepseek-chat 当 Planner、执行下沉确定性代码/模板，与 §四 P1/P2 完全同构。
- 交互安全：Anthropic Cowork/OpenAI ChatGPT Agent（watch mode+后果性动作强制接管）/Copilot Vision（per-session per-permission）均把 **pause-and-confirm 产品化**；OSWorld 2.0 甚至把 **Proactive ASK_USER 做成评测维度**。红线层应从"拦截"升级为 **L0 静默 / L1 执行后报告 / L2 先展示操作清单再确认 / L3 拒绝** 四级。

> D 组一句话诊断（原文）：失败链条 ≈ grounding → 次生环境噪声 → 无状态校验 → 无法回退 → 循环耗尽 → 误判不可行提前放弃——**每一环都是工程可干预的**。

---

## 三、机制 → 痛点对位表（A/B/C/D 四组证据齐）

| HAJIMI 断点 | 开源已验证对策 | 出处与量化证据 | 迁移成本 |
|---|---|---|---|
| ①感知截扁、同名义肢 | 控件树投影序列化（type/patterns/enabled/路径）+ 10 类白名单 + 语义 top-k 过滤；**id×name 交叉验证**；平面编号+SoM 引用 | UFO inspector/`_verify_id`（[docs](https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/overview.md)）；Windows-MCP Snapshot；browser-use DOM 索引（WebVoyager 89.1% vs 纯截图 ~59%） | 低（0.1/0.3 项） |
| ②动作后零验证 | `verify()` 接线 + **WaitFor 后置条件断言**；done 需 `complete_criterion` 独立判据；收尾 judge | Windows-MCP `WaitFor`；Skyvern block criterion；UFO"动作后不得立刻 FINISH"；WAA env-check 判据 | 低（0.2 项，代码已存在） |
| ③无 Replan / 偏航即死 | **Progress Ledger + stall 计数器 → 清历史保账本强制重规划**；7 态 FSM 分级降级；首败即停防放大 | Magentic-One [arXiv:2411.04468](https://arxiv.org/abs/2411.04468)（去账本消融 **-31%**）；UFO FSM；Anthropic batch 首败即停 | 中（1.1/1.2 项） |
| ④长上下文漂移 | 40k 触发式 `<compacted_memory>` 增量重写；8 段模板（含 ERRORS AND FIXES 防重蹈）；外置 TODO.md；观测 masking | browser-use 参数；OpenHands condenser；[Anthropic best-practices](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude) | 低-中（1.3/1.5 项） |
| ⑤动作空间缺口 | ExpandCollapse/右键/拖拽/窗口动作入 API；菜单路径选择器；**投机批量（前置校验+早停）**；错误带 hint | UFO² Algorithm 1（LLM 调用 **-51%**）；mcp-windows `ui_select/ui_batch`；uiacli 错误契约；[API vs GUI arXiv:2501.05446](https://arxiv.org/abs/2501.05446)（API 型 +15-30%） | 低→中（0.5/1.4/1.6） |
| ⑥经验不可回放 | 成功轨迹→参数化 workflow 库（UIA 路径非坐标）+ 确定性回放 + self-heal mini-run | AWM/Voyager/Agent-S（待 B 组补数字）；Skyvern self-heal；[microsoft/cua_skill](https://github.com/microsoft/cua_skill) | 中-高（2.1 项） |
| （天花板校准） | UIA 盲区（UWP/自绘，UFO²：**62% 失败源于控件检测**）→ 二期接 grounding 小模型，主通道仍是 UIA | UFO² [arXiv:2504.14603](https://arxiv.org/abs/2504.14603)；[WebSight](https://arxiv.org/abs/2508.16987)（DOM/AX 残缺镜像证据） | 高（2.3 项，放最后） |

**结构性结论**：六大断点中五个的对策是"纯文本 LLM + UIA 即可落地"的工程件（且 HAJIMI 栈上已有半成品），仅 grounding 盲区需要模型投入——这决定优先级排布：先做 P0/P1 接线，用 2.4 评测台量化，再决定是否为 2.3 花钱。

---

## 四、落地路线（按性价比排序；P0/P1 全部纯文本 LLM + 现有 UIA 栈，不换模型）

> 依据：§二 A/B/C/D 全组证据 + §一 断点编号。行尾括号引用 §二的编号项。

### P0 —— 接线级修复（1-2 天/项，收益立竿见影）

| # | 改造 | 命中断点 | 依据（出处见 §二） | 改动点 |
|---|---|---|---|---|
| 0.1 | **感知序列化升级**：`{id,content}`→投影字段 `id/type/name/class/enabled/patterns/bbox 相对位置/所在容器路径`；10 类 ControlType 白名单 + 语义 top-k 过滤替代"前 30 个"截断；prompt 里空间关系条款改为真实字段或删除 | §1.3-1 | UFO inspector 投影 + 两级过滤；Windows-MCP Snapshot | `uia_bridge._walk/_control_type` + `agent._do_get_screen_info` 返回体 + prompt |
| 0.2 | **动作后验证接线**：act 后强制 `uia_bridge.verify()`（已有！）+ **WaitFor(期望条件)**（Windows-MCP 同款：在调用内轮询文本/控件/焦点出现）；验证失败→自动"重观察"而非继续；删除 done 自评依赖：mark_step_done 前必须有一次成功断言或显式 `complete_criterion` 字段 | §1.3-2 | UFO 机制#3、Skyvern complete_criterion、Anthropic"durable result" | `uia_bridge.act/verify` 返回链 + `agent.execute_step` 循环 + 工具 schema |
| 0.3 | **id×name 交叉验证**：click/type 参数强制带 `name`，服务端与快照核对，不符即拒绝并回报真名 | §1.3-1 幻觉点击 | UFO `_verify_id` | `agent._do_click/_do_type_text` |
| 0.4 | **零 LLM 卡死检测**：动作哈希滑窗 + 观测指纹停滞（UIA id 集合 sha256，连续 N 步不变→分级 nudge）；同动作同观测 4×/同动作皆错 3× → 回滚到循环起点或熔断 | §1.3-3 局部 | OpenHands stuck 五规则、browser-use 5/8/12 阈值 | `agent.execute_step` 内 ~100 行 |
| 0.5 | **ExpandCollapse/右键/拖拽入动作空间**；删 `get_screen_info` 前全局 ESC 副作用（改为可选 close_popup 显式动作）；`double_click/act` 用 UIA 路径 | §1.3-5 | uiacli 坑单、cwin 三层栈 | `uia_bridge.act` + 工具定义 |
| 0.6 | **错误结构化带 hint**：所有工具返回 `{ok, error_code, message, hint}`，hint 面向 LLM 下一轮自纠 | §1.3-2/3 | uiacli、Skyvern error_code_mapping（业务失败不重试） | `agent.dispatch_tool` 统一包装 |
| 0.7 | **done 证据化 + 防过早放弃**：`mark_step_done` 必带证据（UIA prop diff/文件 stat），无证据拒收；`mark_step_failed` 前必须先给一次"换策略"机会（防 WebArena 54.9% 式提前躺平） | §1.3-2 | WebArena 数据、tinyfish"click landed≠done"、Anthropic durable result | 工具 schema + agent 循环两处小改 |
| 0.8 | **Playwright 式 actionability 前置检查**：动作前校验"唯一解析/可见/Stable(bbox 200ms 不变)/可点(不被遮挡)/启用"，不满足→等待或换目标，**等待条件不等待时间** | §1.3-5 | Playwright actionability、V-Droid 预校验(+17pp 级) | `uia_bridge.act` 入口加谓词链 |

### P1 —— 骨架升级（1-2 周，解决"复杂任务"结构性问题）

| # | 改造 | 命中断点 | 依据 | 说明 |
|---|---|---|---|---|
| 1.1 | **engine FSM 化 + 单 agent 双账本**：外层 step 循环改为显式状态机（EXECUTE/VERIFY/REPLAN/FAIL_UP 分级，FAIL→账本记录 root cause→重规划，ERROR→终止）；每步收尾 5 字段 JSON 自评（progress/in-loop/next…），stall>3 → **清消息历史、保留账本、强制重规划** | §1.3-3 | Magentic-One（消融 -31%）、UFO 7 态 FSM | 计划不再是静态一次性：replan prompt 抄 UFO"先述 root cause，新计划特别避免重蹈覆辙" + 账本"已试败方案"段 |
| 1.2 | **重规划真正接入**：失败步把 `(goal, plan_so_far, ledger: actions_taken/errors_and_fixes/current_state)` 喂回 planner 生成"剩余步计划修订"，取代同指令盲重试 | §1.3-3 | UFO 滚动重规划 + Anthropic 8 段 compaction 模板 | engine.py 内新函数即可，复用现有 plan_steps |
| 1.3 | **长任务上下文治理**：40k 字符触发 `<compacted_memory>` 增量重写（keep_last 6 条）；巨型观测 masking；每步压成 `<step N>` | §1.3-4 | browser-use/OpenHands condenser | agent.py messages 管理 |
| 1.4 | **投机批量动作**：同构低依赖子序列（如表单多字段）一次 LLM 调用产 k 个动作，逐个 UIA `is_enabled/visible` 前置校验后执行，**首败即停→报 partial→触发重规划** | 效率+§1.3-3 | UFO² Algorithm 1（LLM 调用 -51%）、Anthropic batch（探索性流程禁用） | 新工具 `perform_batch([...])`，内部仍走 uia_bridge |
| 1.5 | **外置 TODO.md（任务级）+ 步骤窗口注入**：≥N 步任务把计划落盘文件，每步只注入"当前步+前后各1步+勾选状态"，迷路时读文件 | §1.3-3/4 | Anthropic best-practices | sidecar 工作目录即可 |
| 1.6 | **动作前置条件语义**：`type_text` 目标断言 Edit+enabled；菜单=ExpandCollapse 展开→自动重观察→再选择（消灭菜单坐标盲点） | §1.3-5 | UFO/mcp-windows ui_select | uia_bridge 专用动作 `select_menu_path(items[])` |
| 1.7 | **`run_ui_script` CodeAct 快通道**：批量/表单类步骤让 LLM 生成受限 pywinauto 脚本（白名单 API）→ dry-run 枚举"将操作 N 元素"→过红线→逐步执行带 expect；失败回退逐步循环 | §1.3-5/效率 | CodeAct +20%（17 LLM）、deepseek 写码强于点击 | 新工具 + 受限执行沙箱 |
| 1.8 | **红线层升级为 L0-L3 分级交互**：L0 静默(可逆低影响)/L1 执行后报告/L2 展示操作清单先确认(发送/删除/购买/系统设置)/L3 拒绝；确认卡片带"本会话同类免确认"防疲劳 | 安全×可用性 | Anthropic/OpenAI/Copilot Vision 产品化实践、OSWorld2.0 ASK_USER 维度 | `safety.py` 出口改造 + 事件协议加 step_blocked 真发射 |

### P2 —— 能力扩展（1-2 月，含模型/新模块）

| # | 改造 | 依据 | 备注 |
|---|---|---|---|
| 2.1 | **工作流宏库（AWM/Voyager 式）**：成功轨迹→参数化 JSON workflow（automationId 相对路径+控件文本，非坐标）；同类任务检索→确定性回放，失败→self-heal mini-run（Skyvern 模式）| UFO experience/AWM/Skyvern self-heal；microsoft/cua_skill 同方向 | 替换现有 {app,path,summary} 记忆；B/D 组数字支撑 |
| 2.2 | **语义函数层（API 优先）**：高频 app（Excel/Word/文件管理/浏览器）建类型化 MCP 风格工具（COM/pywinauto 快车道），GUI 动作降为兜底 | arXiv:2501.05446（+15-30%）、UFO hybrid | 每 app 一个 module，safety 层按函数级放行（比"按文本猜测动作"更好审） |
| 2.3 | **grounding 兜底服务**：UIA 稀疏（UWP/自绘）才走视觉模型（OS-Atlas/GUI-Owl 2B 级 API，SoM 输出接回 element_id 体系）；局部 zoom | UFO² 62% 数据=盲区确实存在；WebSight 镜像 | 唯一需要外部模型依赖的项，放最后 |
| 2.4 | **回归评测台（建议提前到 P1 并行做）**：移植 WAA 任务 schema（初始断言+成功判据 env-check oracle），30-50 个真实失败任务+VM 快照沙箱；验收口径用 **All-Pass@4**（RoTS 提出的生产稳定性指标，单次数字不可信） | cua harness（同任务跨环境 90%→9%）、WAA、RoTS All-Pass@4 | **没有它，上面所有改进无法归因**；改进项先在此集上 A/B |
| 2.5 | **自我错误分布蒸馏**：把评测台/线上的失败轨迹按 RoTS 11 类打标，生成"本 agent 常见坑"注入（占比≤0.1 防过度反思） | RoTS：自我分布数据 +5.3 vs 人工 +0.6 | 复用 2.4 的数据管道 |

### 反模式（明确不做）

- ❌ 多 agent 天团（planner/critic/reflector 拆成独立 agent）——MAST：agent 间错位占失败 36.9%；价值降维为账本字段/judge 调用（§2.2-⑥）。
- ❌ 引入 LangGraph/AutoGen 依赖（§2.2-⑤）。
- ❌ 在 done 判定上继续只靠执行 LLM 自评（§1.3-2 教训）。
- ❌ 先换大模型再谈骨架——A/C 组证据显示主要断点全在工程层；且 UFO nonvisual 模式 + Windows-MCP"不依赖 CV"均证明文本路线未到期。
