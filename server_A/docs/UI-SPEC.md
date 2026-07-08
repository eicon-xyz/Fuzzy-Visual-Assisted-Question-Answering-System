# B 端 UI 开发规范 — AgentPanel 组件 v2

> 对应 A 端 Agent Loop Execution Mode | 2026-07-06

---

## 一、面板整体布局

```
┌─────────────────────────────────────────────┐
│ HAJIMI 自动操作助手                   ─ □ ✕ │  ← 蓝色标题栏
├─────────────────────────────────────────────┤
│ [输入指令...                        ] [执行] │  ← 输入区
├─────────────────────────────────────────────┤
│ 📋 任务: 打开记事本并输入Hello,world!  2/2  │  ← 进度文字
│                                             │
│ ✅ 打开记事本应用              launched app │  ← 步骤列表
│ ✅ 在记事本中输入Hello,world!  typed text   │    (QListWidget)
├──────────────────┬──────────────────────────┤
│ [截图预览区域]    │ 📝 执行日志               │
│ (OmniParser      │ > Step 1: 打开记事本应用  │
│  标注图)         │ > 调用 launch_app         │
│                  │ > ✅ launched (tier 1)    │
│                  │ > Step 2: 输入文字...     │
├──────────────────┴──────────────────────────┤
│ [⏹ 停止]                                     │
└─────────────────────────────────────────────┘
```

---

## 二、组件树

```
AgentPanel (QWidget)
├── QVBoxLayout (主布局)
│   ├── 顶部输入栏 (QHBoxLayout)
│   │   ├── QLineEdit "query_input"       ← placeholder: "输入你想让AI做的事..."
│   │   └── QPushButton "execute_btn"     ← text: "执 行"
│   │
│   ├── 进度标题 (QLabel "progress_label") ← text: "就绪" / "📋 任务: xxx  1/2"
│   │
│   ├── 步骤列表 (QListWidget "step_list") ← 每行一个步骤
│   │
│   ├── 下部分割区 (QSplitter 水平)
│   │   ├── 截图预览 (QLabel "screenshot_preview")  ← 固定 320×240，支持缩放
│   │   └── 执行日志 (QPlainTextEdit "log_output")  ← 只读
│   │
│   └── 底部控制栏 (QHBoxLayout)
│       └── QPushButton "stop_btn"       ← "⏹ 停止" (红色)
```

---

## 三、步骤列表项的视觉状态

每个步骤在 `QListWidget` 中用一个带图标和文字的行表示：

| 状态 | 图标/符号 | 文字样式 | 说明 |
|------|----------|---------|------|
| `pending` | ⏳ 灰色 | 正常 | 等待执行 |
| `executing` | 🔄 蓝色 + 加粗 | **加粗** | 正在执行 |
| `done` | ✅ 绿色 | 正常 + 灰色摘要 | 已完成，显示 action_summary |
| `failed` | ❌ 红色 | 红色 | 执行失败 |

**代码示例**：
```python
STATUS_ICONS = {
    "pending":    "⏳",
    "executing":  "🔄",
    "done":       "✅",
    "failed":     "❌",
}

def format_step_text(step: dict) -> str:
    icon = STATUS_ICONS.get(step.get("status", "pending"), "⏳")
    instruction = step.get("instruction", "")
    summary = step.get("action_summary", "")
    if summary:
        return f"{icon}  {instruction}  —  {summary}"
    return f"{icon}  {instruction}"
```

---

## 四、状态枚举（前后端统一）

```python
# 步骤状态
STEP_STATUS = ("pending", "executing", "done", "failed")

# 任务状态
TASK_STATUS = ("idle", "planning", "executing", "completed", "failed", "cancelled")

# SSE 事件类型
SSE_EVENTS = (
    "heartbeat", "step_start", "tool_called", "tool_result",
    "screenshot_updated", "step_done", "step_failed", "log",
    "task_done", "task_failed", "task_cancelled",
)

# 日志级别
LOG_LEVELS = ("info", "warn", "error")
```

---

## 五、Mock 数据（开发 UI 用）

在 UI 开发阶段，不需要连 A 端。直接把下面数据写死在 `AgentPanel` 里测试各种状态：

```python
MOCK_PLAN = {
    "task_id": "mock-task-001",
    "goal": "打开记事本并输入Hello,world!",
    "total_steps": 2,
    "steps": [
        {
            "step_index": 1,
            "instruction": "打开记事本应用",
            "status": "done",
            "action_summary": "launched app '记事本' (tier 1)",
        },
        {
            "step_index": 2,
            "instruction": "在记事本中输入'Hello,world!'",
            "status": "executing",
            "action_summary": None,
        },
    ],
}

MOCK_SSE_EVENTS = [
    {"event": "step_start", "data": {"step_index": 1, "instruction": "打开记事本应用"}},
    {"event": "log", "data": {"level": "info", "message": "调用 launch_app('记事本')"}},
    {"event": "screenshot_updated", "data": {"step_index": 1, "annotated_image": "<base64>"}},
    {"event": "step_done", "data": {"step_index": 1, "action_summary": "launched app '记事本' (tier 1)"}},
    {"event": "step_start", "data": {"step_index": 2, "instruction": "在记事本中输入'Hello,world!'"}},
    {"event": "screenshot_updated", "data": {"step_index": 2, "annotated_image": "<base64>"}},
    {"event": "step_done", "data": {"step_index": 2, "action_summary": "typed 'Hello,world!'"}},
    {"event": "task_done", "data": {"task_id": "mock-001", "goal": "...", "total_steps": 2, "completed_steps": 2}},
]

MOCK_LOGS = [
    {"level": "info", "message": "Planning: 打开记事本并输入Hello,world! (2 steps)", "timestamp": "20:30:01"},
    {"level": "info", "message": ">>> Step 1: 打开记事本应用", "timestamp": "20:30:02"},
    {"level": "info", "message": "Round 0: launch_app({'app_name': '记事本'}) → success=True", "timestamp": "20:30:02"},
    {"level": "info", "message": "Layer 1 (mapping): '记事本' → 'notepad.exe'", "timestamp": "20:30:02"},
    {"level": "info", "message": ">>> Step 2: 在记事本中输入'Hello,world!'", "timestamp": "20:30:06"},
    {"level": "info", "message": "Round 1: type_text → success=True", "timestamp": "20:30:08"},
    {"level": "info", "message": "typed 'Hello,world!' into element", "timestamp": "20:30:09"},
]
```

**预览图片 mock**: 收到 `screenshot_updated` 事件时，解码 `annotated_image` base64 → QPixmap。Mock 阶段用灰色占位 QPixmap(320, 240) + "截图预览" 文字。

---

## 六、SSE 事件 → UI 更新 映射表

B 端收到 SSE 事件后，对应的 UI 操作：

| SSE event | UI 更新 |
|-----------|---------|
| `heartbeat` | 忽略（保活用） |
| `step_start` | 该步骤状态 → executing，高亮加粗，日志追加 |
| `tool_called` | 日志追加 "调用 tool_name(args)" |
| `tool_result` | 日志追加结果摘要 |
| `screenshot_updated` | 解码 base64 → QPixmap → 更新截图预览 |
| `step_done` | 该步骤 → done ✅，显示 action_summary |
| `step_failed` | 该步骤 → failed ❌，日志标红 |
| `log` | 追加到日志区（按 level 着色） |
| `task_done` | 所有未完成步骤标记 done，显示总耗时，按钮恢复 |
| `task_failed` | 日志标红显示失败原因，停止按钮禁用 |
| `task_cancelled` | 当前步骤标为 failed，日志显示 "用户取消" |

---

## 七、按钮状态机

| 当前状态 | 执行 | 停止 |
|---------|------|------|
| **idle** (就绪) | 可点击 | 禁用 |
| **executing** (执行中) | 禁用 | 可点击 |
| **completed** (完成) | 可点击 | 禁用 |
| **failed** (失败) | 可点击 | 禁用 |
| **cancelled** (取消) | 可点击 | 禁用 |

---

## 八、开发顺序建议

| 步骤 | 内容 | 预估 |
|------|------|------|
| 1 | 创建 `AgentPanel(QWidget)`，搭好布局骨架 | 1h |
| 2 | 用 mock 数据填充步骤列表，切换状态图标 | 1h |
| 3 | 写日志追加逻辑 + 着色 | 30min |
| 4 | 截图预览区域（支持 base64 解码 + 缩放） | 30min |
| 5 | 按钮状态机逻辑 | 30min |
| 6 | 对接 SSE 客户端线程 | 2h |
| 7 | 集成到 main_widget | 30min |

**总计 ~6h，加调试留 2h 余量，一天足够。**
