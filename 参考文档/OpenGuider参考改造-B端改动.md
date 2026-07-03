# OpenGuider 参考改造 — B 端改动

> 本文档列出 A 端改造后，B 端（HAJIMI_UI）需配合的改动
> 每项均标注"阻塞关系"：A 端未改前，B 端是否可独立开发
> 日期：2026-07-03

---

## 改动总览

| # | 关联 A 端 | 改动范围 | 工时 | 阻塞关系 |
|---|----------|---------|------|---------|
| B1 | #4 风险评分 | 步骤卡片风险图标 | 1h | 非阻塞（UI 先行，A 端字段后续填充） |
| B2 | #6 HITL 执行 | 审批弹窗 + 信任选择器 + step 循环改造 | 8h | 阻塞（需 A 端 `paused` action + `trust_level` 字段） |
| B3 | #3 Multi-Provider LLM | Provider 设置面板 | 3h | 非阻塞（UI 先行） |
| B4 | #5 插件接口 | 插件启停/状态面板 | 4h | 非阻塞（UI 先行） |
| B5 | #2 Pipeline | 坐标校验失败提示 | 1h | 非阻塞 |

**总计 17 工时**。其中 B3/B4/B1/B5 共 9h 可先做，B2 的 8h 等 A 端 #6 完成后再做。

---

## B1. 步骤卡片风险图标 [1h]

### 参考 OpenGuider

`StepApprovalCard.js:108-113` 中每步审批卡渲染以下视觉元素：

```javascript
const riskColor = ['', '#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444'][riskScore];
const riskLabel = ['', 'Safe', 'Low risk', 'Moderate', 'High risk', 'Dangerous'][riskScore];
const riskIcon  = ['', '✅', '🟢', '⚠️', '🔶', '🛑'][riskScore];
```

三个独立视觉通道（颜色 + 文字 + 图标）确保色盲用户也能识别。

### 改动位置

`HAJIMI_UI/ui/native/medium_panel.py` — `_render_step_card()` 方法

### 改动内容

在每张步骤卡片的右侧追加风险指示器：

```
步骤 1: 点击「开始」按钮                    🟢
步骤 2: 输入关键词并回车                     🟢
步骤 3: 删除旧的安装包                       🔴 高风险
```

实现：
```python
_RISK = {
    1: ("#4CAF50", "低风险"),
    2: ("#4CAF50", "低风险"),
    3: ("#FF9800", "中风险"),
    4: ("#F44336", "高风险"),
    5: ("#F44336", "高风险"),
}

def _render_risk_dot(painter, x, y, risk_score):
    color, tooltip = _RISK.get(risk_score, ("#9E9E9E", "未知"))
    painter.setBrush(QColor(color))
    painter.drawEllipse(x, y, 8, 8)  # 8px 圆点
```

---

## B2. 审批弹窗 + 信任选择器 [8h]

### 参考 OpenGuider

OpenGuider 的审批流程跨越三个层面：

**A. 审批卡 UI** (`renderer/components/step-approval/StepApprovalCard.js:108-180`)
```
┌──────────────────────────────────────┐
│  🛑 HIGH RISK         Risk 4/5       │
│  Action Approval                     │
│                                      │
│  Delete the selected item. This      │
│  action cannot be undone.            │
│                                      │
│  ▶ Technical details (collapsed)     │
│    ┌────────────────────────────────┐│
│    │ { "type": "delete", ... }      ││
│    └────────────────────────────────┘│
│                                      │
│  ☑ Run remaining steps automatically │
│                                      │
│  [✓ Approve (Enter)] [↻ Re-plan (R)] │
│  [✕ Abort all (Esc)]                 │
└──────────────────────────────────────┘
```

**B. 键盘快捷键** (`StepApprovalCard.js:47-61`)
- **Enter** → 批准
- **Esc** → 中止全部
- **R** → 重规划（不在 textarea/input 焦点时）

**C. 防重复提交** (`StepApprovalCard.js:188-194`)
```javascript
_decide(decision) {
    if (this._decisionSentStepId === stepId) return;  // 已发送过
    this._decisionSentStepId = stepId;
    openguider.send('execution:step-decision', { taskId, stepId, decision });
    this._hide();
}
```

**D. Trust Override** (`StepApprovalCard.js:172-179`)
审批卡中的 checkbox 可以一次性切换到 autopilot 模式：
```javascript
document.querySelector('#trust-toggle-cb').addEventListener('change', (e) => {
    if (e.target.checked) {
        openguider.send('execution:trust-override', {
            taskId, newTrustLevel: 'autopilot'
        });
    }
});
```
这个 `execution:trust-override` IPC 会被 `task-orchestrator.js:66-73` 监听并热切换生效。

### 改动内容

#### 2a. 审批弹窗组件（新增·4h）

**新增文件**: `HAJIMI_UI/ui/native/approval_dialog.py`

继承 `QDialog`，非模态（用户可以在等待时看屏幕）：

```python
class StepApprovalDialog(QDialog):
    """步骤审批弹窗（参考 OpenGuider StepApprovalCard）"""
    
    decision_made = pyqtSignal(str, dict)  # decision, {step_id, ...}
    
    def __init__(self, step, risk_score, parent=None):
        super().__init__(parent)
        self._step_id = step.step_index
        self._decision_sent = False
        self._setup_ui(step, risk_score)
        self._start_timer(120)  # 120s 超时自动 skip
        
    def _setup_ui(self, step, risk_score):
        # 风险徽章
        color, label = RISK_COLORS[risk_score]
        risk_badge = QLabel(f"{label} (Risk {risk_score}/5)")
        risk_badge.setStyleSheet(f"background: {color}; color: white; border-radius: 4px;")
        
        # 步骤描述
        desc = QLabel(step.description)
        desc.setWordWrap(True)
        
        # 信任切换 checkbox
        self.trust_toggle = QCheckBox("后续步骤全部自动执行")
        
        # 按钮行
        btn_approve = QPushButton("✓ 确认执行 (Enter)")
        btn_skip = QPushButton("跳过 (S)")
        btn_abort = QPushButton("✕ 中止任务 (Esc)")
        
        btn_approve.clicked.connect(lambda: self._decide("approve"))
        btn_skip.clicked.connect(lambda: self._decide("skip"))
        btn_abort.clicked.connect(lambda: self._decide("abort"))
        self.trust_toggle.toggled.connect(self._on_trust_toggled)
        
    def _decide(self, decision):
        if self._decision_sent:
            return
        self._decision_sent = True
        self.decision_made.emit(decision, {"step_id": self._step_id})
        self.accept()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return:
            self._decide("approve")
        elif event.key() == Qt.Key_Escape:
            self._decide("abort")
        elif event.key() == Qt.Key_S:
            self._decide("skip")
```

#### 2b. 信任级别选择器（修改现有 UI·2h）

**修改位置**: `HAJIMI_UI/ui/native/medium_panel.py` — 状态指示栏

在现有 L2/L3 标签旁增加：

```python
trust_combo = QComboBox()
trust_combo.addItem("不信任")      # paranoid
trust_combo.addItem("平衡（推荐）") # balanced
trust_combo.addItem("自动")        # autopilot
trust_combo.setCurrentIndex(1)
trust_combo.currentIndexChanged.connect(self._on_trust_changed)
```

默认值为 `balanced`（索引 1）。选中值随 `/step` 请求发送（`trust_level` 字段）。

#### 2c. Step 循环改造（修改现有逻辑·2h）

**修改位置**: `HAJIMI_UI/ui/app_controller.py` — `_handle_step_response()`

```python
def _handle_step_response(self, response):
    action = response.get("action")
    # ... 现有分支 ...
    
    elif action == "paused":
        # A 端要求审批 → 弹出审批卡
        step = response.get("next_step")
        risk = step.get("risk_score", 3) if step else 3
        dialog = StepApprovalDialog(step, risk)
        dialog.decision_made.connect(
            lambda d, meta: self._on_approval_decided(d, response["task_id"])
        )
        dialog.show()  # 非模态
        return  # 不推进，等用户决策
    
    # ... 其他分支不变 ...

def _on_approval_decided(self, decision, task_id):
    if decision == "approve":
        # 重新调 /step 带 force=true
        self.api.advance_step(task_id, force=True, trust_level=self.trust_level)
    elif decision == "skip":
        self.api.skip_step(task_id)
    elif decision == "abort":
        self.api.terminate_task(task_id)
```

---

## B3. Provider 设置面板 [3h]

### 参考 OpenGuider

`src/ai/index.js` 的 Provider 抽象模式：

每个 Provider 有独立的：
- `baseUrl`（可自定义，用于代理/本地 Ollama）
- `apiKey`（从 Settings store 读取）
- `model`（用户可选，有默认值）
- Vision 能力（Ollama 默认不支持）

`settings.js` 中 Provider 配置是平铺的 key-value：
```
aiProvider, aiModel
claudeApiKey, claudeBaseUrl (optional)
openaiApiKey, openaiBaseUrl (optional)
geminiApiKey, geminiBaseUrl (optional)
groqApiKey, groqBaseUrl (optional)
openrouterApiKey, openrouterBaseUrl (optional)
ollamaModel, ollamaUrl
```

### 改动内容

**修改位置**: `HAJIMI_UI/ui/native/medium_panel.py` 系统设置面板 → 「AI 模型」分区

```
┌─────────────────────────────────────────────┐
│  AI 模型设置                                │
│                                             │
│  当前 Provider: [ DeepSeek ▼ ]              │
│  API Key:       [ ●●●●●●●●       ] [测试]   │
│  模型:          [ deepseek-chat ▼ ]         │
│  Base URL:      [ https://api.deepseek.com ]│
│                                             │
│  ── 备选 Provider ──                        │
│  ☐ OpenAI     Key: [...___]  [测试]         │
│  ☐ Claude     Key: [...___]  [测试]         │
│  ☐ OpenRouter Key: [...___]  [测试]         │
│  ☐ Ollama     URL:  [http://localhost:11434]│
│                [刷新模型列表]               │
│                                             │
│  [保存] [恢复默认]                          │
└─────────────────────────────────────────────┘
```

**测试连接按钮**: 发送一条极短请求到对应 API（如 `"ping"`），验证 key 有效性，返回 ✓/✗。

**Ollama 刷新模型列表**: 调 `GET /api/tags`，填充模型下拉，与 OpenGuider 的 `fetchOllamaModels()` 一致。

**保存**: 写入 `HAJIMI_UI/.env` 的对应变量，重启嵌入 A 端后生效。

---

## B4. 插件管理面板 [4h]

### 参考 OpenGuider

`settings.js` 中插件部分的 UI 模式：

- 每个已安装插件显示为一张**卡片**：名称、版本、状态指示灯（●运行中 / ○已停止）、描述
- [Download Runtime] 按钮 → `scripts/download-browser-agent.js`
- 信任模式选择器（与全局信任级别联动但可独立覆盖）

Sidecar 管理（`src/plugins/browser/sidecar.js`）的几个关键行为：
- 启动时**自动分配端口**（listen(0) 获取随机空闲端口）
- **健康轮询**：`GET /health`，300ms 起指数退避（×2，上限 2s），15s 截止
- **崩溃检测**：子进程 `exit` 事件 → emit `crashed` → UI 可显示错误提示
- **优雅关闭**：POST /abort → SIGTERM → 3s 后 SIGKILL

### 改动内容

**新增文件**: `HAJIMI_UI/ui/native/plugin_panel.py`

```
┌──────────────────────────────────────────────┐
│  插件管理                                    │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │ 🌐 浏览器自动化           v1.0.0  ● 运行中 ││
│  │ 自动操作网页，填写表单，数据采集           ││
│  │ [禁用]  [重启]             [下载 Runtime]  ││
│  └──────────────────────────────────────────┘│
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │ ⌨️  终端助手              ○ 未安装        ││
│  │ 命令行操作指引与执行                      ││
│  │                    [安装]                 ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

**插件来源**: A 端 `GET /api/admin/plugins`（新增端点，对接 `PluginRegistry.list_all()`）

**Runtime 下载按钮**:
- 调 A 端 `POST /api/admin/plugins/{id}/install`
- 显示进度条
- 参考 OpenGuider `scripts/download-browser-agent.js` 的下载→解压→验证流程

**状态轮询**: 每 5s 调 `GET /api/admin/plugins/status` 获取各插件运行状态

---

## B5. 坐标校验失败提示 [1h]

### 参考 OpenGuider

`interaction-pipeline.js:183-206` 中 postprocess 返回的 confidence 有明确的使用规则：

```javascript
// confidence > 0.5 → 使用修正后坐标，提示 "[Verified: reason]"
// confidence < 0.4 → 使用 fallback 坐标，提示 "[Using fallback]"
// 中间 → 保持 LLM 原始坐标
```

### 改动内容

**修改位置**: `HAJIMI_UI/core/overlay_anno.py` — 覆盖层标注渲染

当 A 端 `Annotation` 附加低置信度标记时（通过在 `label_text` 中追加或在 `detection_meta` 中返回），覆盖层使用不同视觉：

- 置信度 ≥ 0.7：红色标注（现状）
- 置信度 0.5-0.7：**橙色**标注 + 文字后追加 `(~85%)`
- 置信度 < 0.5：**灰色虚线**标注 + tooltip "坐标可能不准确，请手动确认"

```python
def _get_annotation_style(confidence):
    if confidence >= 0.7:
        return QColor("#FF0000"), Qt.SolidLine     # 红色实线
    elif confidence >= 0.5:
        return QColor("#FF9800"), Qt.SolidLine     # 橙色实线
    else:
        return QColor("#9E9E9E"), Qt.DashLine      # 灰色虚线
```

---

## B 端改动顺序排期

```
第 1 批（可立即做，不依赖 A 端任何改动·8h）
  ├── B3. Provider 设置面板 (3h)
  ├── B4. 插件管理面板 (4h)
  └── B1. 风险图标 (1h)

第 2 批（A 端 #2 Pipeline 完成后·1h）
  └── B5. 坐标校验提示 (1h)

第 3 批（A 端 #6 HITL 完成后·8h）
  └── B2. 审批弹窗 + 信任选择器 + step 循环 (8h)
```

**总计 17 工时**。第 1 批的 8h 随时可启动。
