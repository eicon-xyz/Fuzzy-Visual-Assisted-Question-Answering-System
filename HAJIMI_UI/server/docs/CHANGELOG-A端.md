# HAJIMI A 端改动记录

> **维护人**：A 端负责人  
> **最后更新**：2026-06-29  
> **说明**：本文按**时间顺序**记录 A 端（`server/`）从 Demo 初版到「真实视觉检测 + 检验模式」的全部重要改动，便于队友 onboarding 与联调对照。

---

## 接口约定（与 api-contract-demo.yaml 对齐）

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/api/demo/health` | GET | 无 | 健康检查 |
| `/api/demo/process` | POST | `X-Demo-Key` | **必填 `image`**；识图 + 步骤 + 标注 |
| `/api/demo/inspect` | POST | `X-Demo-Key` | **仅检测**；全量 `ui_elements` + SoM 图 |
| `/api/demo/step` | POST | `X-Demo-Key` | 推进/回退/跳过/终止 |
| `/api/demo/clarify` | POST | `X-Demo-Key` | 澄清应答 |
| `/api/demo/report` | POST | `X-Demo-Key` | 审计上报 |

**坐标系**（2026-06-29 起）：
- `bbox`、`annotation.highlight_bbox` 以**截图左上角**为原点
- 单位 = **物理像素**（与 B 端 mss 截图一致）
- 响应携带 `reference_resolution: [width, height]`，B 端据此确认无需 1920×1080 缩放

**ProcessResponse 扩展字段**（向后兼容，Optional）：
- `reference_resolution: [w, h]`
- `detection_meta: { latency_ms, element_count, backend }`

---

## 改动时间线（按发生顺序）

### 阶段 0：A 端 Demo 初版（项目基线）

**目标**：提供 FastAPI 后端，实现 `api-contract-demo.yaml` 定义的核心 API，供 B 端 PyQt 客户端联调。

**已有结构**：

```
server/
├── main.py                 # FastAPI + CORS + 全局异常
├── config.py               # 环境变量
├── requirements.txt        # fastapi, uvicorn, httpx, pydantic...
├── models/schemas.py       # ProcessRequest/Response, UIElement, Step...
├── routes/demo.py          # /health, /process, /step, /clarify, /report
├── services/llm_ai.py      # 意图 + 步骤 + 标注（Demo 简化）
├── services/blueprint.py   # 蓝图状态机
└── storage/memory.py       # 内存任务存储
```

**`/process` 初版逻辑**（`llm_ai.process_query(query)`）：

| 步骤 | 行为 |
|------|------|
| 1 | `classify_intent(query)` — 关键词规则（安装/截图/打开…） |
| 2 | `choose_scenario(query)` → `wechat` / `screenshot` / `default` |
| 3 | `elements = SCENARIO_ELEMENTS[scenario]` — **写死 bbox（1920×1080）** |
| 4 | `generate_steps(query)` — DeepSeek 生成 action/description（**不看截图**） |
| 5 | 第 i 步绑定 `elements[i % len(elements)]`，`build_annotation()` 生成标注 |
| 6 | 返回 `ProcessResponse`；`annotated_image=None` |

**关键局限（改前）**：
- `routes/demo.py` 接收 `ProcessRequest.image`，但**从未传入** `process_query`
- UI 坐标来自 `SCENARIO_ELEMENTS` 模板，与用户真实桌面无关
- DeepSeek 只负责步骤文案，不参与元素定位

**运行约定**：
- 默认端口 **8001**（避开 8000 占用 / WinError 10013）
- 启动：`scripts/start_server.bat` 或 `python -m uvicorn server.main:app --host 127.0.0.1 --port 8001`
- 独立 venv：`server/.venv`（**不要**在 videorag 里 pip install server 依赖，会与 streamlit/starlette 冲突）

**涉及文件**：`main.py`, `config.py`, `routes/demo.py`, `services/llm_ai.py`, `services/blueprint.py`, `storage/memory.py`, `models/schemas.py`

---

### 阶段 1：B↔A 联调与运行脚本（联调期）

**背景**：B 端 `core/api_client.py` 默认连 `http://127.0.0.1:8001`，需稳定启动 A 端与文档说明。

**改动摘要**：

| 项 | 内容 |
|----|------|
| 启动脚本 | `scripts/start_server.bat` — 使用 `server/.venv`，端口检查 |
| 环境脚本 | `scripts/setup_server_env.bat` — 创建 venv、安装 requirements |
| 停止脚本 | `scripts/stop_server.bat` |
| 联调验收 | `scripts/verify_integration.py` — health + process + step |
| 文档 | `server/README.md` — B 端环境变量、端口、注意事项 |
| 蓝图状态 | `llm_ai` 返回 `blueprint.state="executing"`（与 B 端步骤 UI 一致） |

**B 端对接方式**（A 端无代码变更，但需知晓）：
- Header：`X-Demo-Key: hajimi-demo-2026`
- Body：`{ "query": "...", "image": "data:image/png;base64,..." }`
- B 端 `_source=server` 表示命中 A 端而非本地 Mock

---

### 阶段 2：环境配置修复 + DeepSeek Key（2026-06-29）

**问题 1**：`config.py` 使用 `load_dotenv()` 无路径，从**项目根**启动 uvicorn 时读不到 `server/.env`。

**改前**：
```python
load_dotenv()
```

**改后**（`server/config.py`）：
```python
load_dotenv(Path(__file__).resolve().parent / ".env")
```

**问题 2**：DeepSeek API Key 未配置，LLM 步骤生成回退 Mock 文案。

**处理**：
- 创建 `server/.env`（已在 `.gitignore`，勿提交）
- 填入 `DEEPSEEK_API_KEY=sk-...`
- 更新 `server/.env.example` 模板

**涉及文件**：`server/config.py`, `server/.env`, `server/.env.example`

---

### 阶段 3：真实视觉检测 + `/inspect` 检验端点（2026-06-29，主重构）

**背景**：B 端已能截屏上传，但 A 端仍用模板坐标；需要 Replicate OmniParser 真实检测，并新增检验 API 供 B 端「全量框选验收」。

#### 3.1 新增模块

| 文件 | 职责 |
|------|------|
| `services/image_utils.py` | `decode_image()` — 解析 Base64 / data URI → PIL RGB |
| `services/ui_detector.py` | `detect()` — Replicate OmniParser V2，输出 `List[UIElement]` |
| `services/som_renderer.py` | `render_base64()` — OpenCV 画 SoM 标注图 |

**检测器接口**（可插拔，便于后续内网 OmniParser）：
```python
@dataclass
class DetectionResult:
    elements: List[UIElement]
    reference_resolution: Tuple[int, int]
    latency_ms: int
    backend: str  # "replicate_omniparser"

def detect(pil_image: Image.Image) -> DetectionResult
```

**OmniParser 模型 ID**（与 B 端旧 `ui_parser.py` 一致）：
```
microsoft/omniparser-v2:49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df
```

**元素编号规则**：按阅读顺序（上→下、左→右）排序后分配 `~1`, `~2`, …

#### 3.2 `process_query` 流水线重构

**改前**：
```
query → SCENARIO_ELEMENTS → generate_steps → elements[i % N] → ProcessResponse
（忽略 image）
```

**改后**：
```
query + image_b64
  → decode_image()
  → ui_detector.detect()
  → som_renderer.render_base64()
  → classify_intent()                    # 保留规则
  → call_deepseek_with_elements()        # 新增：LLM 选 target_element_id
  → pick_fallback_element()              # 校验 / 文本匹配 fallback
  → build_annotation()                   # bbox 来自真实检测
  → ProcessResponse + reference_resolution + detection_meta
```

**新增 LLM Prompt**（`SYSTEM_PROMPT_WITH_ELEMENTS`）：
- 输入：用户问题 + 压缩元素列表（`~id`, type, text, center）
- 输出：`steps[{ action, description, target_element_id }]`

**`SCENARIO_ELEMENTS` 处置**：不再作为默认路径；仅当 `ALLOW_DETECTOR_FALLBACK=1` 且检测失败时使用。

#### 3.3 路由层 `routes/demo.py`

**`/process` 改前**：
```python
response = process_query(request.query)
```

**`/process` 改后**：
```python
if settings.REQUIRE_IMAGE and not request.image:
    raise HTTPException(400, code=MISSING_IMAGE)
response = process_query(request.query, image_b64=request.image)
```

**新增 `POST /api/demo/inspect`**：
- 仅调用 `inspect_image(image_b64)` → 检测 + SoM，**不**生成 task/steps/LLM
- 错误码：`400` 缺图 / `422` 无元素 / `502` 检测器失败

#### 3.4 Schema 扩展 `models/schemas.py`

- `ProcessResponse`：`reference_resolution`, `detection_meta`
- 新增 `InspectRequest`, `InspectResponse`

#### 3.5 配置与依赖

**`config.py` 新增**：
```
DETECTOR_BACKEND=local_omniparser   # 或 replicate_omniparser
OMNIPARSER_LOCAL_URL=http://127.0.0.1:8000
OMNIPARSER_LOCAL_TIMEOUT=120
REPLICATE_API_TOKEN=...
```

**`requirements.txt` 新增**：
```
replicate>=0.25.0
Pillow>=9.0
opencv-python-headless>=4.5
numpy>=1.21
```

**契约同步**：根目录 `api-contract-demo.yaml` 补充 `/inspect` 与 `reference_resolution`

**涉及文件**：
`ui_detector.py`, `som_renderer.py`, `image_utils.py`, `llm_ai.py`, `demo.py`, `schemas.py`, `config.py`, `requirements.txt`, `.env.example`, `api-contract-demo.yaml`

---

### 阶段 4：Replicate 传参 Bug 修复（2026-06-29）

**现象**（B 端检验模式）：
```
HTTP 502 DETECTOR_FAILED
OmniParser replicate call failed: Object of type bytes is not JSON serializable
```

**原因**：`replicate.run(input={ "image": img_bytes })` 中 `bytes` 无法 JSON 序列化。

**改前**（`ui_detector.py`）：
```python
output = replicate.run(model, input={"image": img_bytes, ...})
```

**改后**：
```python
image_input = f"data:image/png;base64,{base64.b64encode(img_bytes).decode('ascii')}"
output = replicate.run(model, input={"image": image_input, ...})
```

**补充**：调用前 `os.environ.setdefault("REPLICATE_API_TOKEN", settings.REPLICATE_API_TOKEN)` 确保 token 生效。

**涉及文件**：`server/services/ui_detector.py`

**验证**：重启 A 端后，B 端 Settings →「立即检测当前屏幕」应不再出现上述 502。

---

### 阶段 5：本地 OmniParser 接入（2026-06-30）

**背景**：Replicate 402 余额不足，改本地 `omniparserserver`。

**A 端改动**：
- `DETECTOR_BACKEND=local_omniparser`
- `OMNIPARSER_LOCAL_URL=http://127.0.0.1:8002`（8000 易被占用时可改端口）
- `ui_detector._detect_local_omniparser()` → `POST {url}/parse/` + `parsed_content_list`

**本地环境（独立于 server/.venv）**：
```powershell
scripts\setup_omniparser.bat    # 克隆 E:\Tools\OmniParser + conda omni + ModelScope 权重
scripts\start_omniparser.bat      # CPU 模式 omniparserserver :8002
scripts\start_server.bat          # A 端 :8001
```

**RTX 50 系注意**：当前 PyTorch 2.6+cu124 不支持 sm_120，默认 **CPU 推理**（~5s/帧）。待 PyTorch nightly 支持后可改 `--device cuda`。

**权重下载**：国内推荐 ModelScope `AI-ModelScope/OmniParser-v2.0` + `Florence-2-base`；HuggingFace 直连可能失败。

**启动顺序**：① `start_omniparser.bat` → ② `start_server.bat` → ③ B 端 `python main.py`

---

### 阶段 6：检验模式超时与 UX 修复（2026-06-30）

**现象**（B 端 Settings →「立即检测当前屏幕」）：
- 前端报 `502 DETECTOR_FAILED` 或超时，但 OmniParser 终端仍在跑 `/parse/`（~120s/次）
- 用户重复点击导致 OmniParser **串行排队**（lock），一次检验实际等待 2–4 分钟甚至更久

**根因**：
1. CPU 全屏检测耗时 **120–240s**，若 B 端 `INSPECT_TIMEOUT` 偏短或未重启加载新配置，客户端先断开
2. B 端断开后 A 端/OmniParser **不会取消**正在进行的解析（设计如此）
3. 检验按钮未禁用，失败后用户再次点击 → OmniParser 日志出现多次连续 `/parse/`

**改动**：

| 层 | 改动 |
|----|------|
| B 端 `config.py` | `INSPECT_TIMEOUT` / `PROCESS_TIMEOUT` 默认 **360s** |
| B 端 `api_client.py` | 正确识别 `socket.timeout`；检验前读 `/health` 的 `omniparser_ready`；502/超时友好中文提示 |
| B 端 UI | 检测中禁用「立即检测」按钮 + 提示「CPU 约 2–4 分钟，请勿重复点击」 |
| A 端 `/health` | 新增 `detector_backend`、`omniparser_ready`（probe :8002） |
| A 端 | `OMNIPARSER_LOCAL_TIMEOUT` 默认 **360s** |

**正确使用检验模式**：
1. 先启动 OmniParser，等到 `Omniparser initialized`
2. 再启动 A 端、B 端（**改代码后需重启 B 端**以加载 360s 超时）
3. 点击「立即检测」后 **只点一次**，等待 2–4 分钟
4. 若报错，先看 OmniParser 终端是否仍在 `start parsing...` — 在跑就等它结束，不要立刻重试

**涉及文件**：`config.py`, `core/api_client.py`, `core/inspect_worker.py`, `ui/main_widget.py`, `ui/native/medium_panel.py`, `server/routes/demo.py`, `server/models/schemas.py`, `server/config.py`

---

### 阶段 8：OmniParser 空白屏 500 + 服务生命周期（2026-06-30）

**502 根因（`local OmniParser HTTP 500`）**：
- OmniParser `get_som_labeled_img` 在 **无 OCR/无图标**（纯色或极简桌面）时 `int_box_area` 解包空 bbox → HTTP 500
- 端口 **8001 多开旧版 A 端**（无 `detector_backend`）时 health/预检不一致

**修复**：
- `scripts/patch_omniparser.py`：`int_box_area` 容错 + 无元素时返回空 `parsed_content_list`（`start_omniparser.bat` 自动执行）
- B 端设置页：启动/停止后端、`stop_all.bat` 联动；关闭窗口默认停止 :8001/:8002
- `api_client.check_process_preflight()`：任务前预检，提示 `stop_all` + `start_all`

**涉及文件**：`scripts/patch_omniparser.py`, `server/services/ui_detector.py`, `core/service_manager.py`, `config.py`, `ui/main_widget.py`, `ui/native/medium_panel.py`

---

### 阶段 7：检验快速失败诊断（2026-06-30）

**现象**：
- 点击「立即检测」后 CPU 2→70→2（数秒内回落），OmniParser 终端**无** `start parsing...`
- 用户误以为「没反应」或「OmniParser 坏了」，实际请求未进入 A→OmniParser 检测链路

**根因**：
- B 端本地截图 + PNG 编码会产生短暂 CPU 峰值（2560×1600），**不等于** OmniParser 在跑
- 若 A 端未就绪、`omniparser_ready=false`、或旧版 A 端无 health 字段，请求在预检阶段即失败，OmniParser 不会收到 `/parse/`

**快速失败排查表**：

| 观察 | 含义 | 处理 |
|------|------|------|
| CPU 秒级 70%→2%，OmniParser 无 parse 日志 | 仅 B 端截图/编码，未进检测链路 | 运行 `python scripts/diagnose_inspect.py` |
| `health` 无 `omniparser_ready` | 旧版 A 端 | 重启 `scripts\start_server.bat` |
| `omniparser_ready: false` | OmniParser 未启动 | 先 `scripts\start_omniparser.bat` |
| A 端有 `POST /inspect` 但 OmniParser 无 parse | A 端 `DETECTOR_BACKEND` 或 URL 错误 | 检查 `server/.env` |
| OmniParser 有 parse，B 端仍报错 | 超时或重复点击排队 | 只点一次，等 2–4 分钟 |

**改动**：

| 层 | 改动 |
|----|------|
| B 端 `api_client.py` | 新增 `check_inspect_preflight()` / `fetch_health()` |
| B 端 `main_widget.py` | 点击检验前先预检，失败则不启动 worker（避免白跑截图） |
| B 端 `inspect_worker.py` | 分阶段 `[inspect]` 控制台日志 |
| A 端 `demo.py` | `/inspect` 收到请求时打印 detector/url/图像尺寸 |
| 脚本 | 新增 `scripts/diagnose_inspect.py`（`--full` 可选跑 parse） |

**诊断命令**：

```cmd
python scripts/diagnose_inspect.py
python scripts/diagnose_inspect.py --full
```

**检验前必查**：`curl http://127.0.0.1:8001/api/demo/health` 应含 `"detector_backend":"local_omniparser"` 且 `"omniparser_ready":true`。

---

## 重构对照速查（改前 → 改后）

| 模块 | 改前 | 改后 |
|------|------|------|
| `/process` 入参 | 只用 `query` | 必填 `image`（`REQUIRE_IMAGE=true`） |
| UI 元素来源 | `SCENARIO_ELEMENTS` 1920×1080 模板 | `ui_detector.detect()` 真实截图 |
| 步骤-元素绑定 | `elements[i % N]` | LLM `target_element_id` + fallback |
| `annotated_image` | 恒 `None` | SoM Base64（process + inspect） |
| 坐标参考 | 隐含 1920×1080 | `reference_resolution` = 截图尺寸 |
| 检验 API | 无 | `POST /api/demo/inspect` |
| 检测后端 | 无 | Replicate OmniParser V2 |

---

## 错误码一览

| HTTP | code | 场景 |
|------|------|------|
| 400 | `MISSING_IMAGE` | `/process` 未传 image |
| 400 | `INVALID_IMAGE` | Base64 解码失败 |
| 401 | `AUTH_FAILED` | `X-Demo-Key` 错误 |
| 422 | `NO_ELEMENTS_DETECTED` | 检测成功但 0 个元素 |
| 502 | `DETECTOR_FAILED` | Replicate 调用失败（含 token、网络、序列化错误） |
| 404 | `NOT_FOUND` | step/clarify 时 task_id 不存在 |

---

## 环境变量完整清单

见 [`server/.env.example`](../.env.example)。**生产/联调必填**：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek 步骤生成 + 元素绑定 |
| `REPLICATE_API_TOKEN` | OmniParser 视觉检测 |
| `HAJIMI_DEMO_KEY` | 与 B 端 `HAJIMI_DEMO_KEY` 一致 |

---

## 验收清单

```powershell
# 1. 安装依赖（仅 server/.venv）
scripts\setup_server_env.bat

# 2. 配置 server\.env（DEEPSEEK + REPLICATE）

# 3. 启动
scripts\start_server.bat

# 4. 健康检查
curl http://127.0.0.1:8001/api/demo/health

# 5. B↔A 联调脚本（1×1 测试图可能 SKIP process/inspect，属正常）
python scripts\verify_integration.py

# 6. 真实截图：B 端 Settings →「立即检测当前屏幕」
```

**真实 `/inspect` curl 示例**（需替换 `<BASE64>` 为桌面截图）：
```powershell
curl -X POST http://127.0.0.1:8001/api/demo/inspect `
  -H "Content-Type: application/json" `
  -H "X-Demo-Key: hajimi-demo-2026" `
  -d "{\"image\": \"data:image/png;base64,<BASE64>\"}"
```

---

## 待 A 端 / 与 B 端联调事项

- [ ] `server/README.md` 第 118–119 行仍写「坐标由规则生成」，需更新为 OmniParser 描述
- [x] 内网部署 OmniParser：新增 `DETECTOR_BACKEND=local_omniparser`，HTTP 调用 `omniparserserver :8000`
- [ ] SeeClick / YOLO 评估（见下方路线图）
- [ ] `ProcessResponse` 可选返回 `reference_resolution` 写入 OpenAPI example

---

## 检测器路线图

| 方案 | 状态 | 说明 |
|------|------|------|
| **Replicate OmniParser V2** | ✅ 可选 | 全量 SoM，2–5s，需 `REPLICATE_API_TOKEN` |
| **内网 OmniParser** | ✅ 当前 | `DETECTOR_BACKEND=local_omniparser`，`scripts/start_omniparser.bat` |
| **SeeClick** | 🔬 评估 | 擅长单步 grounding，不擅长全量 SoM |
| **YOLO + UI 微调** | 🔬 评估 | 本地极速 proposals |
| **Rasa NLU** | ❌ 不适用 | 仅文本意图，无 bbox |

---

## 附录：B 端依赖的 A 端行为（给队友对照）

| B 端行为 | A 端要求 |
|----------|----------|
| 启动探测 health | `/api/demo/health` 返回 `{ status: "ok" }` |
| 提交任务 process | 必须传 `image`；返回 `ui_elements`, `reference_resolution` |
| 检验模式 inspect | `/api/demo/inspect` 可用 |
| 步骤推进 step | `task_store` 内存存 task；`/step` 状态机 |
| 坐标绘制 | bbox 已是截图物理像素；`reference_resolution` 与 B 端 `_screen_size` 一致 |

---

## 变更日志索引（按日期）

| 日期 | 摘要 | 主要文件 |
|------|------|----------|
| 项目基线 | FastAPI Demo + 模板 bbox + DeepSeek 文案 | `llm_ai.py`, `demo.py` |
| 联调期 | 脚本、README、端口 8001、blueprint executing | `scripts/*`, `README.md` |
| 2026-06-29 | `.env` 加载路径修复 + DeepSeek Key | `config.py`, `.env` |
| 2026-06-29 | 真实视觉检测 + `/inspect` + schema 扩展 | `ui_detector.py`, `llm_ai.py`, `demo.py`, … |
| 2026-06-29 | Replicate image 改 data URI（修 502） | `ui_detector.py` |
