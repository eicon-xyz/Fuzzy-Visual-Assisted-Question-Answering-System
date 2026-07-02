# HAJIMI Demo API 接口契约

> **版本**：1.0.0  
> **用途**：Demo 阶段前后端（A-后端/AI 与 B-前端/PyQt5）对齐接口  
> **覆盖流程**：屏幕截图 → AI 识图理解 → 生成操作步骤 → 输出屏幕标注坐标

---

## 一、基本信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://localhost:8000` |
| 协议 | HTTP/1.1（Demo 阶段暂不用 HTTPS） |
| 认证方式 | `X-Demo-Key: hajimi-demo-2026` |
| 请求格式 | `application/json` |
| 响应格式 | `application/json` |

**所有请求都必须在 Header 中携带：**

```http
X-Demo-Key: hajimi-demo-2026
Content-Type: application/json
```

---

## 二、接口总览

| 端点 | 方法 | 用途 | Demo 阶段是否必须 |
|------|------|------|------------------|
| `/api/demo/health` | GET | 服务健康检查 | ✅ |
| `/api/demo/process` | POST | **核心**：截图+问题 → 返回步骤+标注 | ✅ |
| `/api/demo/step` | POST | 推进/回退/跳过/终止步骤 | ✅ |
| `/api/demo/clarify` | POST | 用户回答澄清问题 | ⚠️ 可选 |
| `/api/demo/report` | POST | 任务结束审计上报 | ✅ |

---

## 三、接口详情

### 1. 健康检查

```http
GET /api/demo/health
```

**用途**：前端启动时探测后端是否可用。无需认证。

**响应示例**：

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### 2. 核心流程入口

```http
POST /api/demo/process
```

**用途**：前端上传截图与用户问题，后端返回带标注坐标的操作步骤。

#### 请求体

```json
{
  "query": "怎么安装微信？",
  "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "window_title": "桌面",
  "context": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户自然语言提问 |
| `image` | string | ❌ | 屏幕截图 Base64。Demo 阶段可传空，后端返回预置 Mock 数据 |
| `window_title` | string | ❌ | 当前窗口标题，用于意图理解 |
| `context` | array | ❌ | 最近 3 轮对话上下文 |

#### 响应体

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "intent": {
    "category": "operation_guide",
    "summary": "安装微信",
    "reference_type": "explicit",
    "confidence": 0.92,
    "needs_clarification": false
  },
  "ui_elements": [
    {
      "element_id": "~1",
      "bbox": [120, 340, 240, 380],
      "element_type": "icon",
      "text": "Microsoft Edge",
      "confidence": 0.95,
      "center": [180, 360]
    },
    {
      "element_id": "~2",
      "bbox": [860, 620, 1020, 660],
      "element_type": "button",
      "text": "下载",
      "confidence": 0.91,
      "center": [940, 640]
    }
  ],
  "annotated_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "blueprint": {
    "name": "安装微信",
    "total_steps": 3,
    "current_step": 1,
    "state": "pending_confirm"
  },
  "steps": [
    {
      "step_index": 1,
      "action": "打开浏览器",
      "description": "找到桌面上的 Microsoft Edge 图标，双击打开浏览器。",
      "target_element_id": "~1",
      "status": "active",
      "annotation": {
        "type": "arrow_highlight",
        "arrow_from": [50, 360],
        "arrow_to": [180, 360],
        "highlight_bbox": [120, 340, 240, 380],
        "label_position": [120, 296],
        "label_text": "~1"
      }
    },
    {
      "step_index": 2,
      "action": "访问微信官网",
      "description": "在浏览器地址栏输入 weixin.qq.com 并回车。",
      "target_element_id": "~2",
      "status": "pending",
      "annotation": {
        "type": "highlight_only",
        "highlight_bbox": [860, 620, 1020, 660]
      }
    },
    {
      "step_index": 3,
      "action": "点击下载按钮",
      "description": "在官网首页找到「下载」按钮并点击。",
      "target_element_id": "~2",
      "status": "pending",
      "annotation": {
        "type": "arrow_highlight",
        "arrow_from": [50, 640],
        "arrow_to": [940, 640],
        "highlight_bbox": [860, 620, 1020, 660],
        "label_position": [860, 576],
        "label_text": "~2"
      }
    }
  ]
}
```

#### 关键字段说明

| 字段 | 说明 |
|------|------|
| `task_id` | 本次任务唯一 ID，后续 step/clarify/report 都要携带 |
| `ui_elements[].element_id` | SoM 编号，如 `~1`、`~2`，全局唯一 |
| `ui_elements[].bbox` | 边界框 `[x1, y1, x2, y2]`，坐标系为截图左上角原点 |
| `steps[].status` | `pending` / `active` / `done` / `skipped` / `failed` |
| `blueprint.state` | `pending_confirm` 表示等待用户确认是否执行 |
| `annotated_image` | 带编号标注的完整截图，前端可直接显示 |

#### 前端处理流程

```
1. 调用 /api/demo/process
2. 收到 response 后：
   a. 显示 steps[0] 的 action/description 在文字区
   b. 根据 steps[0].annotation 在覆盖层绘制箭头/高亮框/编号标签
   c. 可选显示 annotated_image 作为调试辅助
3. 用户操作完成后，调用 /api/demo/step 推进
```

---

### 3. 推进蓝图步骤

```http
POST /api/demo/step
```

**用途**：用户完成一步后，前端调用此接口推进、回退、跳过或终止蓝图。

#### 请求体

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "advance",
  "step_index": 1,
  "fingerprint": "a1b2c3d4e5f6789012345678901234567890abcdef"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | ✅ | process 返回的任务 ID |
| `action` | string | ✅ | `advance` / `rollback` / `skip` / `terminate` |
| `step_index` | int | ❌ | 当前步骤序号，用于校验 |
| `fingerprint` | string | ❌ | 当前屏幕指纹 SHA256 |

#### 响应体（成功推进）

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "advance",
  "current_step": 2,
  "blueprint_state": "executing",
  "next_step": {
    "step_index": 2,
    "action": "访问微信官网",
    "description": "在浏览器地址栏输入 weixin.qq.com 并回车。",
    "target_element_id": "~2",
    "status": "active",
    "annotation": {
      "type": "highlight_only",
      "highlight_bbox": [860, 620, 1020, 660]
    }
  }
}
```

#### 响应体（任务完成）

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "complete",
  "current_step": 3,
  "blueprint_state": "completed",
  "message": "任务已完成"
}
```

#### 响应体（挂起）

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "suspended",
  "current_step": 2,
  "blueprint_state": "suspended",
  "message": "检测到屏幕状态与预期不符，您要跳过此步还是回退重试？"
}
```

---

### 4. 主动澄清应答

```http
POST /api/demo/clarify
```

**用途**：当 `process` 返回 `needs_clarification=true` 时，前端展示问题，用户回答后调用此接口。

#### 请求体

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "answer": "我想保存当前打开的 Word 文档"
}
```

#### 响应体

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "confidence": 0.93,
  "needs_clarification": false,
  "question": null,
  "updated_intent": {
    "category": "operation_guide",
    "summary": "保存 Word 文档",
    "reference_type": "context",
    "confidence": 0.93,
    "needs_clarification": false
  }
}
```

> 注：Demo 阶段如果 `needs_clarification` 仍返回 true，前端可继续提问并再次调用本接口。

---

### 5. 审计与反馈上报

```http
POST /api/demo/report
```

**用途**：任务结束后，前端异步上报执行结果和用户反馈。Demo 阶段后端只记录到日志，不写入数据库。

#### 请求体

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "result": "success",
  "feedback_type": "useful",
  "duration_ms": 5200,
  "comment": "指引很清晰"
}
```

#### 响应体

```json
{
  "received": true
}
```

---

## 四、核心数据模型

### UIElement（UI 元素）

```json
{
  "element_id": "~1",
  "bbox": [120, 340, 240, 380],
  "element_type": "icon",
  "text": "Microsoft Edge",
  "confidence": 0.95,
  "center": [180, 360]
}
```

| 字段 | 说明 |
|------|------|
| `element_id` | SoM 编号，格式 `~N` |
| `bbox` | 边界框 `[x1, y1, x2, y2]`，坐标原点为截图左上角 |
| `element_type` | `button` / `input` / `icon` / `menu` / `checkbox` / `dropdown` / `text` / `other` |
| `text` | 元素上的文字，OCR 结果可能为空 |
| `confidence` | 识别置信度 0~1 |
| `center` | 元素中心点 `[cx, cy]`，箭头指向这里 |

### Annotation（标注）

```json
{
  "type": "arrow_highlight",
  "arrow_from": [50, 360],
  "arrow_to": [180, 360],
  "highlight_bbox": [120, 340, 240, 380],
  "label_position": [120, 296],
  "label_text": "~1"
}
```

| 字段 | 说明 |
|------|------|
| `type` | `arrow_highlight` / `highlight_only` / `arrow_only` / `label_only` / `none` |
| `arrow_from` | 箭头起点 `[x, y]` |
| `arrow_to` | 箭头终点 `[x, y]`，指向目标元素中心 |
| `highlight_bbox` | 虚线高亮框 `[x1, y1, x2, y2]` |
| `label_position` | 编号标签左上角 `[x, y]` |
| `label_text` | 标签文字，如 `~1` |

### Step（步骤）

```json
{
  "step_index": 1,
  "action": "打开浏览器",
  "description": "找到桌面上的 Microsoft Edge 图标，双击打开浏览器。",
  "target_element_id": "~1",
  "status": "active",
  "annotation": { ... }
}
```

| 字段 | 说明 |
|------|------|
| `step_index` | 步骤序号，从 1 开始 |
| `action` | 简短动作文案，用于语音播报和标题 |
| `description` | 详细说明，显示在文字区 |
| `target_element_id` | 引用的 SoM 编号 |
| `status` | `pending` / `active` / `done` / `skipped` / `failed` |
| `annotation` | 屏幕标注信息 |

### Blueprint（蓝图）

```json
{
  "name": "安装微信",
  "total_steps": 3,
  "current_step": 1,
  "state": "pending_confirm"
}
```

| state 值 | 含义 |
|----------|------|
| `generated` | 已生成，未锁定 |
| `pending_confirm` | 等待用户确认执行 |
| `executing` | 执行中 |
| `suspended` | 屏幕指纹不匹配，已挂起 |
| `rolling_back` | 正在回退 |
| `completed` | 已完成 |
| `terminated` | 已终止 |

---

## 五、前端 Mock 数据

后端接口未 ready 时，前端 B 可直接使用以下 Mock 响应进行开发。

### Mock `/api/demo/process` 响应

```json
{
  "task_id": "mock-task-001",
  "success": true,
  "intent": {
    "category": "operation_guide",
    "summary": "安装微信",
    "reference_type": "explicit",
    "confidence": 0.92,
    "needs_clarification": false
  },
  "ui_elements": [
    {
      "element_id": "~1",
      "bbox": [120, 340, 240, 380],
      "element_type": "icon",
      "text": "Microsoft Edge",
      "confidence": 0.95,
      "center": [180, 360]
    },
    {
      "element_id": "~2",
      "bbox": [860, 620, 1020, 660],
      "element_type": "button",
      "text": "下载",
      "confidence": 0.91,
      "center": [940, 640]
    }
  ],
  "annotated_image": "",
  "blueprint": {
    "name": "安装微信",
    "total_steps": 3,
    "current_step": 1,
    "state": "pending_confirm"
  },
  "steps": [
    {
      "step_index": 1,
      "action": "打开浏览器",
      "description": "找到桌面上的 Microsoft Edge 图标，双击打开浏览器。",
      "target_element_id": "~1",
      "status": "active",
      "annotation": {
        "type": "arrow_highlight",
        "arrow_from": [50, 360],
        "arrow_to": [180, 360],
        "highlight_bbox": [120, 340, 240, 380],
        "label_position": [120, 296],
        "label_text": "~1"
      }
    },
    {
      "step_index": 2,
      "action": "访问微信官网",
      "description": "在浏览器地址栏输入 weixin.qq.com 并回车。",
      "target_element_id": "~2",
      "status": "pending",
      "annotation": {
        "type": "highlight_only",
        "highlight_bbox": [860, 620, 1020, 660]
      }
    },
    {
      "step_index": 3,
      "action": "点击下载按钮",
      "description": "在官网首页找到「下载」按钮并点击。",
      "target_element_id": "~2",
      "status": "pending",
      "annotation": {
        "type": "arrow_highlight",
        "arrow_from": [50, 640],
        "arrow_to": [940, 640],
        "highlight_bbox": [860, 620, 1020, 660],
        "label_position": [860, 576],
        "label_text": "~2"
      }
    }
  ]
}
```

---

## 六、联调检查清单

### 后端 A 自检

- [ ] FastAPI 服务可启动，访问 `http://localhost:8000/api/demo/health` 返回 `{"status":"ok"}`
- [ ] `POST /api/demo/process` 能接收 query + image，返回合法的 `ProcessResponse`
- [ ] 返回的 `steps` 中每条都有 `annotation` 且坐标在合理范围内
- [ ] `POST /api/demo/step` 能根据 `action=advance` 正确推进 `current_step`
- [ ] `POST /api/demo/report` 能接收并记录日志
- [ ] 缺少 `query` 时返回 400 错误，格式符合统一错误响应

### 前端 B 自检

- [ ] 能捕获屏幕截图并转为 Base64
- [ ] 能正确调用 `POST /api/demo/process` 并解析响应
- [ ] 能在 PyQt5 覆盖层上根据 `annotation` 绘制箭头、虚线框、编号标签
- [ ] 能在文字区显示当前步骤的 `action` 和 `description`
- [ ] 用户点击「下一步」后能调用 `POST /api/demo/step` 并更新界面
- [ ] 任务完成后调用 `POST /api/demo/report` 上报

### 联调共同检查

- [ ] 前端发送请求带 `X-Demo-Key: hajimi-demo-2026`
- [ ] 坐标系一致：均以截图左上角为原点 (0,0)
- [ ] 截图缩放问题：如果前端对截图做了缩放，需在绘制标注时做等比映射
- [ ] 响应中 `ui_elements` 的 `element_id` 与 `steps` 中 `target_element_id` 能对应

---

## 七、统一错误响应

所有错误响应格式统一：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "缺少必填字段 query",
    "details": {}
  }
}
```

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `INVALID_REQUEST` | 400 | 请求参数格式错误或缺少必填字段 |
| `AUTH_FAILED` | 401 | `X-Demo-Key` 无效 |
| `NOT_FOUND` | 404 | `task_id` 不存在 |
| `INTERNAL_ERROR` | 500 | 服务端内部错误（如 LLM 超时） |

---

## 八、快速测试命令

### 测试健康检查

```bash
curl http://localhost:8000/api/demo/health
```

### 测试核心流程

```bash
curl -X POST http://localhost:8000/api/demo/process \
  -H "X-Demo-Key: hajimi-demo-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "怎么安装微信？",
    "window_title": "桌面",
    "context": []
  }'
```

### 测试步骤推进

```bash
curl -X POST http://localhost:8000/api/demo/step \
  -H "X-Demo-Key: hajimi-demo-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "action": "advance",
    "step_index": 1,
    "fingerprint": "mock-fingerprint-hash"
  }'
```

---

## 九、Demo 阶段简化约定

1. **认证简化**：用固定 `X-Demo-Key` 替代 JWT/HMAC，生产阶段再替换。
2. **数据库存储简化**：`task` 状态用内存 dict 保存，服务重启后重置。
3. **步骤生成简化**：Demo 阶段后端直接调 LLM 生成步骤，不走预置蓝图匹配。
4. **指纹校验简化**：`fingerprint` 字段后端仅记录，不做严格匹配，避免 Demo 时频繁挂起。
5. **图片大小限制**：建议单张截图 Base64 后不超过 2MB，超出可压缩或改传 URL。

---

## 十、后续扩展提示

Demo 完成后，如需对齐完整架构，请参考：

- 完整 API 规格：《HAJIMI 详细设计文档》第八部分「接口详细设计」
- 认证方案：JWT Access Token（2h）+ Refresh Token（7d）+ HMAC-SHA256 签名
- 正式端点：`/api/audit/report`、`/api/config/pull`、`/api/admin/*`
