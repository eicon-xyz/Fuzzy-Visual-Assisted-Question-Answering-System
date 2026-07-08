# L5 SSE 契约扩展（8011 Sidecar）

> **范围**：仅 `new_JIMI/HAJIMI_UI` L5 Sidecar（`:8011`）。**8010 主 A 端 / L3/L4 不变。**

## 背景

B 端 L5 UI 需要在「步骤列表」面板展示 **规划步骤 + 每步执行时间线**。Phase 1 已消费现有事件；Phase 2 增加工具级 SSE 供时间线展示每次 Agent 工具调用。

## 现有事件（已实现）

| 事件 | 触发时机 | payload |
|------|----------|---------|
| `step_start` | 步骤开始 | `{step_index, instruction}` |
| `step_done` | 步骤成功 | `{step_index, action_summary}` |
| `step_failed` | 步骤失败 | `{step_index, reason}` |
| `step_blocked` | 安全拦截 | `{step_index, message?}` |
| `log` | 重试/警告 | `{level, message}`（B 端按 step_index 归属当前步） |
| `screenshot_updated` | `get_screen_info` 后 | `{step_index, annotated_image}` |
| `task_done` | 全部完成 | `{task_id, goal, total_steps, completed_steps}` |
| `task_failed` | 中途失败 | `{reason, failed_step}` |
| `task_cancelled` | 用户取消 | `{}` |
| `heartbeat` | 保活 | `{timestamp}` |

## Phase 2 新增事件（Sidecar 已实现，UI 默认隐藏）

| 事件 | 触发时机 | payload |
|------|----------|---------|
| `tool_called` | `dispatch_tool` 前 | `{step_index, tool, args}` |
| `tool_result` | `dispatch_tool` 后 | `{step_index, tool, success, action_summary?, duration_ms, error?}` |

### 示例 SSE 片段

```
event: tool_called
data: {"step_index": 1, "tool": "get_screen_info", "args": {}}

event: screenshot_updated
data: {"step_index": 1, "annotated_image": "data:image/jpeg;base64,..."}

event: tool_result
data: {"step_index": 1, "tool": "get_screen_info", "success": true, "action_summary": "screenshot taken (12 elements)", "duration_ms": 842}

event: tool_called
data: {"step_index": 1, "tool": "double_click", "args": {"element_id": "el_3"}}

event: tool_result
data: {"step_index": 1, "tool": "double_click", "success": true, "action_summary": "double-clicked element 'Recycle Bin'", "duration_ms": 320}

event: step_done
data: {"step_index": 1, "action_summary": "double-clicked element 'Recycle Bin'"}
```

## B 端 Feature Flag

工具级时间线行默认 **不显示**，避免 Sidecar 未升级时出现空行：

```bat
set HAJIMI_L5_TOOL_SSE=1
```

或在 Sidecar health 后续增加 `capabilities.tool_sse=true` 后自动开启。

实现位置：[`HAJIMI_UI/ui/native/l5_timeline.py`](../ui/native/l5_timeline.py) 中 `l5_tool_sse_enabled()`。

## 待 Sidecar 后续实现（P2）

| 能力 | 说明 |
|------|------|
| `POST /api/demo/pause` | Agent 循环检查 pause_event；UI「暂停/继续」按钮 |
| `tool_result.bbox` | 点击坐标回传，供 B 端「L5 桌面标注」overlay |

## 联调检查

1. 重启 8011 Sidecar（加载 `tool_called`/`tool_result`）
2. B 端：`set HAJIMI_L5_TOOL_SSE=1` 后启动 UI
3. L5 任务 → 步骤列表 → 当前步时间线应出现 `→ get_screen_info()` 与 `✓ ... 842ms` 行
