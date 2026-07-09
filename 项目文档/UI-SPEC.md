# B 端 UI 开发规范 — AgentPanel 组件

> 对着这份文档就能写代码，不需要跑 A 端

---

## 一、面板整体布局

```
┌─────────────────────────────────────────────┐
│ HAJIMI 自动操作助手                   ─ □ ✕ │  ← 蓝色标题栏
├─────────────────────────────────────────────┤
│ [输入指令...                        ] [执行] │  ← 输入区
├─────────────────────────────────────────────┤
│ 📋 任务: 安装微信到D盘                 83%  │  ← 进度文字
│                                             │
│ ✅ 打开浏览器                        2.3s   │  ← 步骤列表
│ ✅ 访问下载页                        1.8s   │    (QListWidget)
│ 🔄 点击下载按钮...                          │
│ ⏳ 运行安装程序                              │
│ ⏳ 选择D盘路径                              │
├──────────────────┬──────────────────────────┤
│ [截图预览区域]    │ 📝 执行日志               │
│                  │ > 思考：下一步需点击下载   │
│                  │ > 动作：click(480,525)   │
│                  │ > 等待 2s...             │
│                  │ > 验证：步骤完成 ✅       │
├──────────────────┴──────────────────────────┤
│ [▶ 开始(Ctrl+1)] [⏸ 暂停(Ctrl+2)]           │
│ [▶ 恢复(Ctrl+3)] [⏹ 停止(Ctrl+4)] 红色      │
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
│   ├── 进度标题 (QLabel "progress_label") ← text: "就绪" / "📋 任务: xxx  83%"
│   │
│   ├── 步骤列表 (QListWidget "step_list") ← 每行一个步骤
│   │
│   ├── 下部分割区 (QSplitter 水平)
│   │   ├── 截图预览 (QLabel "screenshot_preview")  ← 固定 320×240
│   │   └── 执行日志 (QPlainTextEdit "log_output")  ← 只读
│   │
│   └── 底部控制栏 (QHBoxLayout)
│       ├── QPushButton "start_btn"      ← "▶ 开始"  Ctrl+1
│       ├── QPushButton "pause_btn"      ← "⏸ 暂停"  Ctrl+2
│       ├── QPushButton "resume_btn"     ← "▶ 恢复"  Ctrl+3
│       └── QPushButton "stop_btn"       ← "⏹ 停止"  Ctrl+4 (红色)
```

---

## 三、步骤列表项的视觉状态

每个步骤在 `QListWidget` 中用一个带图标和文字的行表示：

| 状态 | 图标/符号 | 文字样式 | 说明 |
|------|----------|---------|------|
| `pending` | ⏳ 灰色 | 正常 | 等待执行 |
| `active` | 🔄 蓝色 + 加粗 | **加粗** | 正在执行 |
| `done` | ✅ 绿色 | 正常 + 灰色耗时 | 已完成 |
| `failed` | ❌ 红色 | 红色 | 执行失败 |
| `blocked` | 🚫 橙色 | 橙色 | 被安全拦截 |
| `skipped` | ⏭️ 灰色 | 灰色 + 删除线 | 跳过 |

**代码示例**：
```python
STATUS_ICONS = {
    "pending":  "⏳",
    "active":   "🔄",
    "done":     "✅",
    "failed":   "❌",
    "blocked":  "🚫",
    "skipped":  "⏭️",
}

def format_step_text(step: dict) -> str:
    icon = STATUS_ICONS.get(step.get("status", "pending"), "⏳")
    desc = step.get("description", "")
    duration = step.get("duration_ms", 0)
    if step["status"] == "done" and duration:
        return f"{icon}  {desc}    {duration/1000:.1f}s"
    return f"{icon}  {desc}"
```

---

## 四、状态枚举（前后端统一）

```python
# 步骤状态
STEP_STATUS = ("pending", "active", "done", "failed", "blocked", "skipped")

# 任务状态
TASK_STATUS = ("idle", "planning", "executing", "paused", "completed", "failed", "cancelled")

# 操作类型
ACTIONS = ("click", "double_click", "right_click", "type", "press_key", "scroll", "wait", "drag")

# 日志级别
LOG_LEVELS = ("info", "warn", "error", "debug")
```

---

## 五、Mock 数据（开发 UI 用）

在 UI 开发阶段，不需要连 A 端。直接把下面数据写死在 `AgentPanel` 里测试各种状态：

```python
MOCK_PLAN = {
    "task_id": "mock-task-001",
    "goal": "安装微信到D盘",
    "total_steps": 5,
    "steps": [
        {
            "step_index": 1,
            "action": "double_click",
            "description": "双击桌面上的浏览器图标",
            "target_element_id": "~3",
            "bbox": [120, 340, 180, 410],
            "bbox_center": [150, 375],
            "params": None,
            "status": "done",
            "duration_ms": 2300,
        },
        {
            "step_index": 2,
            "action": "type",
            "description": "在地址栏输入微信官网地址",
            "target_element_id": "~7",
            "bbox": [200, 50, 800, 90],
            "bbox_center": [500, 70],
            "params": "weixin.qq.com",
            "status": "done",
            "duration_ms": 1800,
        },
        {
            "step_index": 3,
            "action": "click",
            "description": "点击下载按钮",
            "target_element_id": "~12",
            "bbox": [400, 500, 560, 550],
            "bbox_center": [480, 525],
            "params": None,
            "status": "active",
            "duration_ms": 0,
        },
        {
            "step_index": 4,
            "action": "double_click",
            "description": "运行安装程序",
            "target_element_id": "~5",
            "bbox": [100, 600, 160, 660],
            "bbox_center": [130, 630],
            "params": None,
            "status": "pending",
            "duration_ms": 0,
        },
        {
            "step_index": 5,
            "action": "click",
            "description": "选择安装路径为D盘",
            "target_element_id": "~18",
            "bbox": [700, 500, 800, 540],
            "bbox_center": [750, 520],
            "params": None,
            "status": "pending",
            "duration_ms": 0,
        },
    ],
}

MOCK_LOGS = [
    {"level": "info", "message": "AI 正在规划执行步骤...", "timestamp": "20:30:01"},
    {"level": "info", "message": "生成5个执行步骤", "timestamp": "20:30:03"},
    {"level": "info", "message": ">>> 步骤1: 双击桌面浏览器图标", "timestamp": "20:30:04"},
    {"level": "info", "message": "动作: double_click, 坐标: (150,375)", "timestamp": "20:30:04"},
    {"level": "info", "message": "验证: 浏览器已打开 ✅", "timestamp": "20:30:07"},
    {"level": "info", "message": ">>> 步骤2: 输入微信官网地址", "timestamp": "20:30:08"},
    {"level": "info", "message": "动作: type \"weixin.qq.com\"", "timestamp": "20:30:08"},
    {"level": "info", "message": "验证: 地址栏已输入 ✅", "timestamp": "20:30:11"},
    {"level": "info", "message": ">>> 步骤3: 点击下载按钮", "timestamp": "20:30:12"},
    {"level": "info", "message": "动作: click(480,525)", "timestamp": "20:30:12"},
    {"level": "warn", "message": "点击后页面无变化，重试中...", "timestamp": "20:30:15"},
]
```

**预览图片 mock**: 用 `QPixmap(320, 240)` 填充灰色+文字"截图预览"，或加载一张本地测试图片。

---

## 六、SSE 事件 → UI 更新 映射表

B 端收到 SSE 事件后，对应的 UI 操作：

| SSE event | UI 更新 |
|-----------|---------|
| `plan_ready` | 填充步骤列表（全部 pending），显示 goal，清空日志 |
| `step_start` | 该步骤状态 → active，高亮，日志追加"开始执行步骤 N" |
| `step_executing` | 日志追加 detail |
| `step_done` | 该步骤 → done ✅，显示耗时，刷新截图预览 |
| `step_failed` | 该步骤 → failed ❌，日志标红 |
| `step_retry` | 日志追加"正在重试..." |
| `step_blocked` | 该步骤 → blocked 🚫，日志标橙 |
| `log` | 追加到日志区（按 level 着色） |
| `screenshot` | 解码 base64 → QPixmap → 更新截图预览 |
| `task_done` | 所有未完成步骤标记为 done，显示总耗时，按钮恢复 |
| `task_error` | 日志标红显示错误信息，停止按钮可点击 |
| `heartbeat` | 忽略（保活用） |

---

## 七、按钮状态机

| 当前状态 | 开始 | 暂停 | 恢复 | 停止 |
|---------|------|------|------|------|
| **idle** (就绪) | 可点击 | 禁用 | 禁用 | 禁用 |
| **executing** (执行中) | 禁用 | 可点击 | 禁用 | 可点击 |
| **paused** (暂停) | 禁用 | 禁用 | 可点击 | 可点击 |
| **completed** (完成) | 可点击 | 禁用 | 禁用 | 禁用 |
| **failed** (失败) | 可点击 | 禁用 | 禁用 | 可点击 |
| **cancelled** (取消) | 可点击 | 禁用 | 禁用 | 禁用 |

---

## 八、开发顺序建议

| 步骤 | 内容 | 预估 |
|------|------|------|
| 1 | 创建 `AgentPanel(QWidget)`，搭好布局骨架 | 1h |
| 2 | 用 mock 数据填充步骤列表，切换状态图标 | 1h |
| 3 | 写日志追加逻辑 + 着色 | 30min |
| 4 | 截图预览区域（先用灰色占位） | 30min |
| 5 | 按钮状态机逻辑 | 1h |
| 6 | 对接 SSE 客户端线程 | 2h |
| 7 | 集成到 main_widget（替换旧面板） | 30min |

**总计 ~6.5h，加调试留 2h 余量，一天足够。**
