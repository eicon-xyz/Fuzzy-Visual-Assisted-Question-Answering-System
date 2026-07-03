# LLM 元素感知与动态重规划实施计划

> 本文档解决 HAJIMI 当前的核心瓶颈：LLM 在制定操作计划时看不到当前屏幕的实际 UI 元素，导致步骤与界面元素随机绑定；以及首次截图无法覆盖多步骤任务中后续屏幕的元素，需要动态重规划机制。

---

## 一、当前问题诊断

### 1.1 数据流现状

```
用户输入 "安装微信"
    │
    ├─ [Bridge.sendUserInput] → TaskWorkerThread → POST /process
    │
    ├─ [process_query] server/services/llm_ai.py:288
    │   ├─ OmniParser 解析截图
    │   │     └─ elements = [{~1, button, "下载"}, {~2, icon, "Edge"} ...]
    │   │                                          ↑
    │   ├─ generate_steps(query)  ← LLM 看不到 elements  ← 断裂点 ①
    │   │     └─ call_deepseek(SYSTEM_PROMPT 纯文本) → 返回 steps
    │   │
    │   ├─ 步骤绑定：elements[i % len(elements)]       ← 随机绑定 ②
    │   │     └─ 步骤 1 说"点击下载"，但指向了 Edge 图标
    │   │
    │   └─ build_annotation(element) → 生成 overlay 坐标
    │
    └─ [Bridge._sync_frontend] → overlay 渲染
```

### 1.2 两大核心问题

| 问题 | 表现 | 影响 |
|------|------|------|
| **断裂点 ①** | LLM 制定计划时未获得 `ui_elements` 列表 | 步骤描述与目标元素脱节，无法语义匹配 |
| **随机绑定 ②** | `elements[i % len(elements)]` 机械循环 | 用户按指引点击时会点到错误的控件 |
| **静态蓝图 ③** | `/process` 只基于第一张截图生成完整计划 | 多屏操作（如安装软件）中后续步骤无法精确标注 |

### 1.3 关键发现

- `Step.target_element_id` 字段已存在于 `server/models/schemas.py:70`，但从未被 LLM 填充。
- `ProcessResponse.ui_elements` 会返回给前端，但前端不消费该字段（前端只使用 `step.annotation`）。
- `ProcessResponse.annotated_image` 当前恒为 `None`。
- 前端 `annotation_mapper.py` 只消费 `annotation.highlight_bbox` / `arrow_from` / `arrow_to`，不关心元素绑定逻辑。

---

## 二、总体架构目标

引入**两阶段能力**：

| 阶段 | 目标 | 核心能力 |
|------|------|---------|
| **P0：元素感知** | 让 LLM 在初始规划时就能看到 OmniParser 输出的元素列表，实现语义绑定 | 静态蓝图中的步骤精准指向当前屏幕可见元素 |
| **P2：动态重规划** | 当用户执行到无元素绑定的步骤时，自动截取新屏幕，重新解析并填充后续步骤的绑定 | 多屏长流程（安装、设置、网页操作）端到端精准标注 |

最终交互形态：

```
用户说"安装微信"
    │
    ▼ 桌面截图 + OmniParser
    Step 1: 打开浏览器 → 绑定 Edge 图标（红框标注）
    Step 2: 访问微信官网 → 暂无绑定（文字指引）
    │
    ▼ 用户打开浏览器 → 触发重规划
    Step 2: 访问微信官网 → 绑定地址栏（红框标注）
    Step 3: 点击下载 → 暂无绑定
    │
    ▼ 用户进入微信官网 → 触发重规划
    Step 3: 点击下载 → 绑定下载按钮（红框标注）
```

---

## 三、P0：LLM 元素感知实施细节

### 3.1 改动范围

只修改 `server/services/llm_ai.py`，约 120 行改动。前端与数据模型无需变动。

### 3.2 新增：元素序列化函数

将 `List[UIElement]` 转换为 LLM 可读文本。

```python
def _serialize_elements(elements: List[UIElement], max_count: int = 25) -> str:
    """将 UI 元素列表序列化为 LLM prompt 文本"""
    if not elements:
        return "（未检测到 UI 元素）"

    sorted_els = sorted(elements, key=lambda e: e.confidence, reverse=True)[:max_count]
    lines = []
    for e in sorted_els:
        text = e.text.strip() if e.text else "(无文本)"
        lines.append(
            f"  {e.element_id}: {e.element_type} \"{text}\" (置信度:{e.confidence:.2f})"
        )
    return "\n".join(lines)
```

**规则说明**：

- 按置信度降序排列，优先让 LLM 看到高置信度元素。
- 上限 25 个，控制 token 消耗。
- 元素数为 0 时提示"未检测到 UI 元素"，LLM 仍可生成纯文字指引。

### 3.3 改造 SYSTEM_PROMPT

新 prompt 包含：元素列表占位符、输出格式、匹配规则、3 个 few-shot 示例。

```python
SYSTEM_PROMPT = """你是一个桌面操作指引助手。

你的任务：分析下方"当前屏幕 UI 元素"列表，理解用户指令，将操作分解为 2-5 步，并明确指出每一步对应哪个 UI 元素。

## 当前屏幕 UI 元素
{element_list}

## 输出格式
严格按以下 JSON 格式返回，不要 markdown 代码块：
{{
  "steps": [
    {{
      "action": "简短动作",
      "description": "给用户的详细说明",
      "target_element_id": "~3"
    }}
  ]
}}

规则：
1. 每一步必须从"当前屏幕 UI 元素"中选择最匹配的元素。
2. 如果某一步在当前屏幕没有对应元素（如"等待下载完成"），`target_element_id` 必须为空字符串 `""`。
3. 不要为没有可见元素的概念性步骤硬编元素 ID。

## 元素匹配规则
- "按钮"优先 `type=button`；"输入框/搜索框"优先 `type=input`；"图标"优先 `type=icon`。
- 优先选择 `text` 字段与用户语义最接近的元素。
- 有多个候选时，按位置常识辅助判断：右下角常见"确认/下载/下一步"，右上角常见"关闭/设置"，中部常见"主要内容区"。
- 置信度低于 0.70 的元素尽量不要选。

## 示例 1（桌面场景）
当前屏幕 UI 元素：
  ~1: icon "Microsoft Edge" (置信度:0.95)
  ~2: icon "此电脑" (置信度:0.93)
  ~3: icon "回收站" (置信度:0.92)
  ~4: button "开始" (置信度:0.96)

用户："安装微信"
输出：
{{
  "steps": [
    {{"action": "打开浏览器", "description": "双击桌面上的 Microsoft Edge 图标", "target_element_id": "~1"}},
    {{"action": "访问微信官网", "description": "在浏览器地址栏输入 weixin.qq.com 并回车", "target_element_id": ""}},
    {{"action": "点击下载", "description": "在微信官网首页找到下载按钮并点击", "target_element_id": ""}},
    {{"action": "运行安装程序", "description": "下载完成后，双击安装包按提示完成安装", "target_element_id": ""}}
  ]
}}

## 示例 2（登录窗口）
当前屏幕 UI 元素：
  ~1: input "用户名" (置信度:0.90)
  ~2: input "密码" (置信度:0.90)
  ~3: button "登录" (置信度:0.95)
  ~4: button "忘记密码" (置信度:0.85)

用户："我要登录"
输出：
{{
  "steps": [
    {{"action": "输入用户名", "description": "在用户名输入框中输入你的账号", "target_element_id": "~1"}},
    {{"action": "输入密码", "description": "在密码输入框中输入你的密码", "target_element_id": "~2"}},
    {{"action": "点击登录", "description": "点击登录按钮进入系统", "target_element_id": "~3"}}
  ]
}}

## 示例 3（消歧）
当前屏幕 UI 元素：
  ~1: button "确定" (置信度:0.93)  ← 弹出窗口中的确定
  ~2: button "取消" (置信度:0.91)
  ~3: button "确定" (置信度:0.88)  ← 主窗口中的确定

用户："点确定"
输出：
{{
  "steps": [
    {{"action": "点击确定", "description": "点击当前弹出窗口中的确定按钮", "target_element_id": "~1"}}
  ]
}}
"""
```

### 3.4 改造 LLM 调用链

#### 3.4.1 `call_deepseek()` 增加 elements 参数

```python
def call_deepseek(
    query: str,
    elements: Optional[List[UIElement]] = None,
    timeout: int = 30,
) -> Optional[List[dict]]:
    if not settings.DEEPSEEK_API_KEY:
        return None

    element_text = _serialize_elements(elements)
    prompt = SYSTEM_PROMPT.format(element_list=element_text)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={...},
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,  # 元素列表较长时适当增加
                },
            )
            # ...
            return parse_llm_steps(content)
    except Exception as e:
        print(f"[LLM Error] {type(e).__name__}: {e}")
        return None
```

#### 3.4.2 `generate_steps()` 传递 elements

```python
def generate_steps(query: str, elements: Optional[List[UIElement]] = None) -> List[dict]:
    if settings.USE_REAL_LLM:
        llm_steps = call_deepseek(query, elements=elements)
        if llm_steps:
            return llm_steps

    # Mock fallback（见 3.5）
    scenario = choose_scenario(query)
    return _MOCK_FALLBACKS[scenario]
```

#### 3.4.3 `process_query()` 使用 LLM 返回的 `target_element_id`

```python
def process_query(query: str, image_base64: Optional[str] = None) -> ProcessResponse:
    # ... 意图理解 ...

    # 获取元素（OmniParser 或 mock）
    if image_base64:
        parsed_elements = parse_screenshot(image_base64)
        elements = parsed_elements if parsed_elements else SCENARIO_ELEMENTS[scenario].copy()
    else:
        elements = SCENARIO_ELEMENTS[scenario].copy()

    # 生成步骤（传入元素列表）
    raw_steps = generate_steps(query, elements)

    # 按 element_id 索引元素
    element_by_id = {e.element_id: e for e in elements}

    steps: List[Step] = []
    for i, raw in enumerate(raw_steps):
        step_index = i + 1
        target_id = raw.get("target_element_id", "")
        element = element_by_id.get(target_id) if target_id else None

        if element:
            annotation = build_annotation(
                element,
                annotation_type="arrow_highlight" if step_index == 1 else "highlight_only",
                label_text=element.element_id,
            )
        else:
            annotation = None

        steps.append(
            Step(
                step_index=step_index,
                action=raw["action"],
                description=raw["description"],
                target_element_id=target_id if element else None,
                status="pending",
                annotation=annotation,
            )
        )

    if steps:
        steps[0].status = "active"

    # ... 构建 Blueprint 与 ProcessResponse ...
```

**关键语义变化**：

- `target_element_id = "~3"` 且元素存在 → 生成标注。
- `target_element_id = ""` 或元素不存在 → 无标注，纯文字步骤。
- 这比原有"每步机械绑定"更合理：并非每个操作步骤都有当前屏幕元素对应。

### 3.5 补全 Mock Fallback 数据

为 mock 场景步骤也加上 `target_element_id`：

```python
_MOCK_FALLBACKS = {
    "wechat": [
        {"action": "打开浏览器", "description": "找到桌面上的浏览器图标，双击打开。", "target_element_id": "~1"},
        {"action": "访问微信官网", "description": "在地址栏输入 weixin.qq.com 并回车。", "target_element_id": ""},
        {"action": "点击下载按钮", "description": "在官网首页找到「下载」按钮并点击。", "target_element_id": "~2"},
        {"action": "运行安装程序", "description": "下载完成后，双击安装包按提示完成安装。", "target_element_id": ""},
    ],
    "screenshot": [
        {"action": "打开截图工具", "description": "按下 Win + Shift + S 打开系统截图工具。", "target_element_id": "~1"},
        {"action": "选择截图区域", "description": "拖动鼠标选择要截取的区域。", "target_element_id": ""},
        {"action": "保存截图", "description": "截图完成后，点击通知中的预览并保存。", "target_element_id": ""},
    ],
    "default": [
        {"action": "观察当前界面", "description": "仔细查看屏幕上的可点击元素。", "target_element_id": "~1"},
        {"action": "按提示操作", "description": "根据系统指引逐步完成目标。", "target_element_id": ""},
    ],
}
```

### 3.6 P0 测试用例

| 场景 | 输入 | 期望 |
|------|------|------|
| 语义匹配 | "点击下载按钮" + `~2:button "下载"` | `target_element_id: "~2"`，overlay 高亮 |
| 类型-文本匹配 | "输入密码" + `~3:input "密码"` | `target_element_id: "~3"` |
| 概念性步骤 | "等待下载完成" | `target_element_id: ""`，无 overlay |
| LLM 幻觉 ID | LLM 返回 `~99` 但仅 3 个元素 | 安全降级为空，无 overlay |
| OmniParser 失败 | elements 为空 | LLM 仍生成文字步骤，全部 `target_element_id: ""` |
| Mock 降级 | `USE_REAL_LLM=false` | mock 步骤使用预定义绑定 |

---

## 四、P2：动态重规划实施细节

### 4.1 为什么需要动态重规划

P0 解决的是"首次截图中可见元素"的精准绑定。但多数真实任务需要跨越多个屏幕：

- 安装软件：桌面 → 浏览器 → 网页 → 下载弹窗 → 安装向导。
- 系统设置：设置主界面 → 子菜单 → 具体选项。
- 网页操作：搜索页 → 结果页 → 详情页 → 弹窗。

首次截图无法包含后续屏幕的元素。因此当用户推进到无绑定的步骤时，必须截取**当前屏幕**并重新规划未绑定步骤。

### 4.2 渐进式重规划策略

只在没有 `target_element_id` 的步骤被激活时触发重规划，而不是每步都重规划。

```
用户完成 Step 1（浏览器打开）
    │
    ▼ Step 2 激活，但 target_element_id=""
    ├─ 前端自动截图
    ├─ POST /step {action:"advance", step_index:2, image:"<新截图>", fingerprint:"..."}
    ├─ 后端解析新图 → new_elements
    ├─ 调用 replan_steps(原始query, Step 2..N, new_elements)
    ├─ LLM 为未绑定步骤填充 target_element_id
    └─ 返回更新后的 Step 2（现在有绑定）
```

**触发条件**（满足其一即可）：

1. 当前步骤 `target_element_id` 为空。
2. 当前步骤 `target_element_id` 非空，但新截图 fingerprint 与存储 fingerprint 差异较大（用户已离开预期界面）。
3. 用户主动点击"重新定位当前步骤"按钮。

### 4.3 接口变更

#### 4.3.1 `StepRequest` 增加 `image` 字段

```python
class StepRequest(BaseModel):
    task_id: str
    action: str = Field(..., pattern="^(advance|rollback|skip|terminate)$")
    step_index: Optional[int] = Field(None, ge=1)
    fingerprint: Optional[str] = None
    image: Optional[str] = Field(
        None,
        description="新截图 Base64；用于无绑定步骤的动态重规划",
    )
```

#### 4.3.2 `/step` 路由增加重规划分支

```python
@router.post("/step")
async def step(request: StepRequest, demo_key: str = Depends(verify_demo_key)):
    state = task_store.get(request.task_id)
    if not state:
        raise HTTPException(...)

    # ... 确认蓝图逻辑 ...

    engine = BlueprintEngine()
    if request.action == "advance":
        action, next_step = engine.advance(state, settings.STRICT_FINGERPRINT)
    # ... rollback / skip / terminate ...

    # === 动态重规划 ===
    if (
        request.image
        and next_step
        and not next_step.target_element_id
    ):
        new_elements = parse_screenshot(request.image)
        if new_elements:
            updated_steps = replan_steps(
                original_query=state.query,
                current_step_index=state.blueprint.current_step - 1,
                all_steps=state.steps,
                new_elements=new_elements,
            )
            # 用更新后的 steps 替换旧 steps，并保持状态
            for i, updated in enumerate(updated_steps):
                if state.blueprint.current_step - 1 <= i < len(state.steps):
                    state.steps[i] = updated
            next_step = state.steps[state.blueprint.current_step - 1]

    state.fingerprint = request.fingerprint
    task_store.update(state)

    return StepResponse(
        task_id=state.task_id,
        action=action,
        current_step=state.blueprint.current_step,
        blueprint_state=state.blueprint.state,
        next_step=next_step,
        message=message,
    )
```

### 4.4 后端重规划函数

在 `server/services/llm_ai.py` 中新增：

```python
REPLAN_PROMPT = """你是一个桌面操作指引助手。当前用户正在执行一个多步骤任务，现在需要为后续未绑定界面元素的步骤补充目标元素。

## 用户的原始请求
{original_query}

## 当前屏幕 UI 元素
{element_list}

## 尚未绑定元素的后续步骤
{upcoming_steps}

## 要求
1. 对于"当前屏幕 UI 元素"中明显可匹配到元素的步骤，补全 `target_element_id`。
2. 若某一步在当前屏幕仍无匹配元素（如下一步会打开新窗口/弹窗），`target_element_id` 保持为空字符串 `""`。
3. 输出格式与初始规划一致：
{{
  "steps": [
    {{"action": "...", "description": "...", "target_element_id": "~1"}}
  ]
}}

注意：只需返回需要更新的步骤，保持 action 和 description 不变，只修改 target_element_id。
"""


def _serialize_steps_for_replan(steps: List[Step]) -> str:
    lines = []
    for s in steps:
        lines.append(
            f"  Step {s.step_index}: [{s.action}] {s.description} → current_target={s.target_element_id or '(空)'}"
        )
    return "\n".join(lines)


def replan_steps(
    original_query: str,
    current_step_index: int,
    all_steps: List[Step],
    new_elements: List[UIElement],
) -> List[Step]:
    """基于新截图的元素列表，为未绑定步骤填充 target_element_id"""
    unbound_steps = [
        s for s in all_steps[current_step_index:] if not s.target_element_id
    ]

    if not unbound_steps or not new_elements:
        return all_steps

    element_text = _serialize_elements(new_elements)
    upcoming_text = _serialize_steps_for_replan(unbound_steps)

    prompt = REPLAN_PROMPT.format(
        original_query=original_query,
        element_list=element_text,
        upcoming_steps=upcoming_text,
    )

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "请为上述步骤补全 target_element_id。"},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1200,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            replanned = parse_llm_steps(content) or []
    except Exception as e:
        print(f"[Replan Error] {e}")
        return all_steps

    # 合并结果
    element_by_id = {e.element_id: e for e in new_elements}
    updated_steps = list(all_steps)

    for raw in replanned:
        step_index = raw.get("step_index")
        target_id = raw.get("target_element_id", "")

        # 若 LLM 未返回 step_index，按顺序匹配
        if step_index is None:
            continue

        idx = step_index - 1
        if 0 <= idx < len(updated_steps):
            element = element_by_id.get(target_id) if target_id else None
            if element:
                updated_steps[idx].target_element_id = target_id
                updated_steps[idx].annotation = build_annotation(
                    element,
                    annotation_type="highlight_only",
                    label_text=target_id,
                )
            else:
                updated_steps[idx].target_element_id = None
                updated_steps[idx].annotation = None

    return updated_steps
```

### 4.5 前端触发逻辑

在 `HAJIMI_UI/ui/main_widget.py` 的 `_request_step_action()` 中：

```python
def _request_step_action(self, action: str):
    if not self.task_id or not self.steps:
        return

    step_index = self.current_step_index + 1  # 1-based
    current_step = self.steps[self.current_step_index]

    # 是否需要截图触发重规划：当前步骤无绑定且是 advance 操作
    needs_screenshot = (
        action == "advance"
        and not current_step.get("target_element_id")
    )

    image_base64 = None
    fingerprint = self.fingerprint
    if needs_screenshot:
        screenshot = capture_screen()
        if screenshot is not None:
            image_base64 = pil_to_data_uri(screenshot)
            fingerprint = compute_fingerprint(screenshot)

    try:
        response = api_advance_step(
            self.task_id,
            step_index,
            fingerprint or "",
            action,
            self.steps,
            image=image_base64,
        )
    except Exception as exc:
        self.sig_add_message.emit(f"步骤推进失败: {exc}", "system danger")
        return

    self._handle_step_response(response, action)
```

并在 `HAJIMI_UI/core/api_client.py` 中的 `advance_step()` 增加 `image` 参数。

### 4.6 P2 测试用例

| 场景 | 输入 | 期望 |
|------|------|------|
| 浏览器打开后重规划 | Step 2 无绑定 + 新截图含地址栏 input | `target_element_id` 指向地址栏 |
| 进入官网后重规划 | Step 3 无绑定 + 新截图含下载 button | `target_element_id` 指向下载按钮 |
| 仍无匹配元素 | 新截图仍未出现目标 | 保持空，纯文字指引 |
| 用户回退 | action="rollback" | 不触发重规划 |
| 网络异常 | LLM 调用失败 | 返回原步骤，不崩溃 |

---

## 五、文件改动清单

| 文件 | P0 改动 | P2 改动 |
|------|---------|---------|
| `server/services/llm_ai.py` | ✅ 新增 `_serialize_elements()`，改造 `SYSTEM_PROMPT`、`call_deepseek()`、`generate_steps()`、`process_query()`，补 mock 数据 | ✅ 新增 `REPLAN_PROMPT`、`replan_steps()` |
| `server/models/schemas.py` | ❌ 不改动 | ✅ `StepRequest.image` 字段 |
| `server/routes/demo.py` | ❌ 不改动 | ✅ `/step` 路由增加重规划分支 |
| `server/services/blueprint.py` | ❌ 不改动 | ❌ 不改动 |
| `HAJIMI_UI/core/api_client.py` | ❌ 不改动 | ✅ `advance_step()` 增加 `image` 参数 |
| `HAJIMI_UI/ui/main_widget.py` | ❌ 不改动 | ✅ `_request_step_action()` 截图触发逻辑 |
| 前端 overlay/JS | ❌ 不改动 | ❌ 不改动 |

---

## 六、实施时间线

| 阶段 | 任务 | 预计工时 | 前置条件 |
|------|------|---------|---------|
| **P0** | LLM 元素感知实现 | 3-4h | 无 |
| **P0** | 单元测试与 API 自测 | 1-2h | P0 代码完成 |
| **P2** | 动态重规划接口与后端逻辑 | 3-4h | P0 完成 |
| **P2** | 前端截图触发逻辑 | 2-3h | P2 接口完成 |
| **P2** | 端到端流程测试 | 2-3h | P2 前后端完成 |
| **合计** | — | **11-16h** | — |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DeepSeek token 消耗增加 | 每次调用约增加 500-1000 tokens 元素列表 | `max_tokens` 调至 1500；元素上限 25 |
| 重规划延迟 | 每触发一次约 2-4 秒（OmniParser + LLM） | 仅无绑定步骤触发，已绑定步骤零延迟 |
| LLM 返回无效 ID | 绑定失败 | `element_by_id.get()` 安全降级为空 |
| 用户移动过快 | 截图时屏幕还在变化 | 重规划时加入短暂防抖（300-500ms） |
| 多步骤任务过长 | 累积 token 和状态复杂 | 一次只重规划未绑定步骤，不重新生成历史 |

---

## 八、最终交付标准

完成 P0 + P2 后，系统应能流畅完成如下演示：

1. 用户说"安装微信"，系统识别桌面上的 Edge 图标并高亮。
2. 用户双击打开浏览器后，系统自动识别浏览器地址栏并高亮。
3. 用户进入微信官网后，系统自动识别下载按钮并高亮。
4. 若某一步骤在当前屏幕没有对应元素，系统给出纯文字说明，不误导。
5. 整个过程 LLM 调用次数受控，不超出经济成本。

---

## 附录：术语说明

- **SoM（Set-of-Mark）**：给 UI 元素贴编号标签（~1, ~2），作为 LLM 与界面元素的中间语言。
- **OmniParser**：微软开源的屏幕 UI 元素检测模型，输出元素 bbox、类型、文本。
- **静态蓝图**：任务开始时一次性生成完整步骤序列。
- **动态重规划**：任务执行过程中根据新截图更新后续步骤的元素绑定。
- **few-shot prompt**：在 prompt 中给出示例，引导 LLM 按期望格式输出。
