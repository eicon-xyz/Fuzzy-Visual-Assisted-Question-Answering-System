# A 端后端开发清单 — Day 1–4

> 负责人 A | 2026-07-04

---

## Day 1（今天）：恢复管道 + LLM 重写

### ✅ Task 1: 恢复 OmniParser 配置 (30min)

**文件**: `server/config.py`

在 `Config` 类中添加：
```python
# OmniParser 远程 GPU
OMNIPARSER_URL: str = os.getenv("OMNIPARSER_URL", "http://127.0.0.1:9800")
OMNIPARSER_TIMEOUT: int = int(os.getenv("OMNIPARSER_TIMEOUT", "30"))
```

同时**删掉**或注释掉已废弃的 `DETECTOR_BACKEND=vision_llm` 相关逻辑。

---

### ✅ Task 2: 恢复 health_check (30min)

**文件**: `server/routes/demo.py`

在 `health_check()` 中恢复 OmniParser 探测：
```python
@router.get("/health", ...)
async def health_check():
    """Health check with OmniParser probe."""
    import httpx
    omni_ready = False
    omni_device = None
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{settings.OMNIPARSER_URL}/probe/")
            if resp.status_code == 200:
                data = resp.json()
                omni_ready = data.get("ready", False)
                omni_device = data.get("device", "unknown")
    except Exception:
        pass

    if not omni_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "omniparser_ready": False,
                     "message": "OmniParser 远程服务不可达"}
        )

    return HealthResponse(
        status="ok",
        version="2.0.0",
        detector_backend="local_omniparser",
        detector_active="local_omniparser",
        detector_device=omni_device or "cuda",
        omniparser_url=settings.OMNIPARSER_URL,
        omniparser_ready=True,
    )
```

---

### ✅ Task 3: 重写 process_query — 核心 (2h)

**文件**: `server/services/planning/router.py`

**改动点**：

**3a)** 在 `process_query()` 函数开头，红线检测之后，插入 OmniParser 调用：

```python
# 0. OmniParser 检测元素
from server.services.omniparser_client import parse_screenshot_full
parse_result = parse_screenshot_full(image_base64)
ui_elements = parse_result.elements
annotated_image = parse_result.annotated_image
reference_resolution = parse_result.reference_resolution
detection_meta = parse_result.detection_meta

if not ui_elements:
    # 空白屏或检测失败
    return ProcessResponse(
        task_id=str(uuid.uuid4()),
        success=False,
        ...
    )
```

**3b)** 将 UI 元素序列化为文本，传给 LLM：

```python
# 序列化
element_lines = []
for el in ui_elements:
    bbox = el.bbox
    cx, cy = el.center or [(bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2]
    element_lines.append(
        f"{el.element_id}: {el.element_type} \"{el.text or ''}\" "
        f"bbox={bbox} center=[{int(cx)},{int(cy)}] conf={el.confidence:.2f}"
    )
element_text = "\n".join(element_lines)
```

**3c)** 重写 LLM prompt — 这是最关键的部分：

```python
EXECUTOR_SYSTEM_PROMPT = """你是一个桌面自动化执行器。你的任务是基于屏幕上的 UI 元素列表，将用户的自然语言指令转化为机器可执行的操作计划。

## 当前屏幕 UI 元素
{element_list}

## 输出格式
严格按以下 JSON 格式返回，不要 markdown代码块：
{{
  "goal": "简短的任务目标描述",
  "steps": [
    {{
      "step_index": 1,
      "action": "click",
      "description": "点击浏览器图标",
      "target_element_id": "~3",
      "bbox": [120, 340, 180, 410],
      "bbox_center": [150, 375],
      "params": null
    }}
  ]
}}

## action 类型
- click: 鼠标左键单击
- double_click: 鼠标左键双击
- right_click: 鼠标右键
- type: 键盘输入文字，params 为要输入的字符串
- press_key: 按组合键，params 为 "ctrl+c" 等
- scroll: 滚轮滚动，params 为正数(向上)或负数(向下)
- wait: 等待，params 为等待秒数
- drag: 拖拽，params 为 [start_x,start_y,end_x,end_y]

## 规则
1. 每一步必须选择当前屏幕上的一个元素，给出其 element_id、bbox、bbox_center。
2. bbox_center 取 bbox 的中心坐标 [cx, cy]，必须是整数。
3. 步骤要原子化：一次只能做一个操作。
4. 如果某一步在当前屏幕上没有对应元素（如"等待下载完成"），action 用 "wait"。
5. 如果用户指定了约束条件（如安装路径、版本），在 params 中体现。
6. 规划 2-8 步，不要超过 10 步。
"""
```

---

### ✅ Task 4: 新增 /execute 端点 (1h)

**文件**: `server/routes/demo.py`

```python
@router.post("/execute")
async def execute_task(request: ProcessRequest, demo_key: str = Depends(verify_demo_key)):
    """接收指令，启动执行计划。返回 task_id 和执行计划。"""
    # 1. 生成执行计划（内部调用 process_query）
    from server.services.planning.router import process_query as plan_query
    response = plan_query(request.query, request.image)

    if not response.success:
        return {
            "success": False,
            "error": {"code": "LLM_FAILED", "message": "规划失败"}
        }

    # 2. 保存到内存
    task_store.create(response, request.query)

    # 3. 后台线程启动执行
    import threading
    from server.services.executor.engine import executor
    thread = threading.Thread(
        target=executor.run_plan,
        args=(response.task_id, [s.model_dump() for s in response.steps]),
        daemon=True
    )
    thread.start()

    # 4. 返回 task_id + plan
    return {
        "task_id": response.task_id,
        "success": True,
        "plan": {
            "goal": response.intent.summary,
            "total_steps": len(response.steps),
            "steps": [s.model_dump() for s in response.steps],
        },
        "screenshot_base64": response.annotated_image,
        "reference_resolution": response.reference_resolution,
        "detection_meta": response.detection_meta,
    }
```

---

### ✅ Task 5: 新增 SSE 端点 (1h)

**文件**: `server/routes/demo.py`

```python
from fastapi.responses import StreamingResponse
import json, time

@router.get("/stream/{task_id}")
async def stream_events(task_id: str):
    """SSE 实时推送执行进度"""
    from server.services.executor.engine import executor

    def generate():
        # 先发心跳确认连接
        yield format_sse("heartbeat", {"timestamp": str(time.time())})

        for event in executor.get_events(task_id):
            yield format_sse(event["event"], event["data"])

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

---

## Day 2: 执行引擎 + 验证循环

### Task 6: 完善 engine.py (3h)

- 实现 `run_plan()` 的完整主循环
- 实现重试逻辑（失败后最多重试 2 次）
- 实现截图验证步骤（调 LLM 看图）
- 使用 Python `queue.Queue` 存储 SSE 事件，供 `/stream` 端点消费

### Task 7: 完善 clicker.py (1.5h)

- `click_at()` 增加坐标边界检查
- `type_text()` 处理中文（用 `pyperclip` 粘贴）
- 增加 `scroll_at()` 实现

### Task 8: 验证函数 (1h)

**文件**: `server/services/llm_ai.py` 新增：

```python
def verify_step(image_base64: str, step_description: str) -> dict:
    """LLM 看图判断步骤是否完成。返回 {status, confidence, rationale}"""
    prompt = f"""这张截图是一个桌面自动化操作执行后的屏幕。
步骤描述: {step_description}
请判断这个步骤是否已经完成。
返回JSON: {{"status": "done|not_done|uncertain", "confidence": 0.95, "rationale": "..."}}"""
    # 调用 call_vision_llm
    ...
```

---

## Day 3: 联调 + 安全

### Task 9: 安全规则完善 (1h)

**文件**: `server/services/executor/safety.py`

- 完善关键词规则表（至少 30 条）
- 增加上下文判断（如"删除"后面跟"文件"才拦截，跟"文字"不拦截）

### Task 10: 端到端联调 (3h)

- 和 B 端联调 SSE
- 准备 5+ 个测试任务（打开记事本、打开计算器、创建文件夹等）
- 修各种边界 bug

---

## Day 4: 修 bug + 交付

### Task 11: 边界处理 (2h)

- OmniParser 超时重试
- LLM 返回格式错误时的修复逻辑
- 执行中用户取消的优雅处理

### Task 12: 测试 + README (2h)

- 端到端过 5 个任务
- 写 README 启动说明

---

## 快速验证命令

```bash
# 测试 OmniParser 连通
curl http://127.0.0.1:9800/probe/

# 测试 A 端健康
curl http://127.0.0.1:8010/api/demo/health

# 测试完整执行（需要 Python）
python -c "
import mss, base64, json, urllib.request
from io import BytesIO
from PIL import Image

# 截图
with mss.mss() as sct:
    img = sct.grab(sct.monitors[1])
    pil = Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX')
    buf = BytesIO()
    pil.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()

# 执行
data = json.dumps({'query':'打开记事本','image':f'data:image/png;base64,{b64}'}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:8010/api/demo/execute',
    data=data,
    headers={'Content-Type':'application/json','X-Demo-Key':'hajimi-demo-2026'}
)
resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
print(f\"task_id: {resp.get('task_id')}\")
print(f\"plan: {resp['plan']['total_steps']} steps\")
for s in resp['plan']['steps']:
    print(f\"  {s['step_index']}. {s['action']} → {s['description']} @ {s['bbox_center']}\")
"
```
