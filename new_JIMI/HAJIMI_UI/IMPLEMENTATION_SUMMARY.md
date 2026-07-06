# HAJIMI_UI 后端优化 — 实施总结

## 目标

将 OpenGuider 0.3.5 的后端优势逆向移植到 HAJIMI_UI（Python FastAPI），同时保留 PyQt5 UI 不动。

**三个项目的关系：**

```
OpenGuider 0.3.5 (Node.js)  ──架构逆向──▶  OpenSource/HAJIMI OG (Python)  ──移植──▶  HAJIMI_UI (Python)
   上游参考                                   已验证的 Python 实现                   本项目
```

---

## 核心改动：移除 OmniParser → 纯视觉 LLM

**之前**：截图 → OmniParser (:8002, CPU每帧2-4分钟) → 元素列表 → LLM → 步骤

**之后**：截图 → 多模态 LLM 直接看图 → `[POINT:x,y:label]` 坐标 + 步骤

> 不再需要 OmniParser 外部服务，LLM API Key 即可运行。

---

## 新建文件一览

### Tier 1：核心 LLM + 代理循环（直接移植自 OpenSource）

| 文件 | 行数 | 功能 |
|------|------|------|
| `server/services/llm/providers.py` | ~330 | 8供应商LLM、`[POINT]`标签解析、JSON修复、自适应重试 |
| `server/services/agent/prompts.py` | ~210 | Plan+Locate组合提示词、Evaluator/Replanner提示词 |
| `server/services/agent/chains.py` | ~280 | `plan_and_locate()`、`evaluate_step()`、`replan_goal()`、`fast_mode_chat()` |
| `server/services/agent/orchestrator.py` | ~310 | `TaskOrchestrator`：完整 Plan→Evaluate→Replan 智能循环 |
| `server/services/session/manager.py` | ~180 | 会话状态机：步骤推进/回退/跳过、指针历史 |
| `server/services/validation/coords.py` | ~55 | 0-1000归一化坐标 ↔ 绝对像素转换、边界裁剪 |
| `server/services/validation/postprocess.py` | ~78 | 跳变检测(>500px)、历史平均平滑(最近5次) |

### Tier 2：缓存 + OCR + 蒸馏 + 嵌入 + 窗口枚举

| 文件 | 行数 | 功能 |
|------|------|------|
| `server/services/cache.py` | ~70 | 900ms TTL截图缓存 + SHA-256指纹去重 |
| `server/services/perception/ocr_engine.py` | ~150 | 本地Tesseract OCR（中英文），惰性初始化 |
| `server/services/context/distiller.py` | ~100 | 快速纯文本LLM预调用，总结屏幕内容减少主调用token |
| `server/services/context/embedding_matcher.py` | ~115 | all-MiniLM-L6-v2 (384维) 余弦相似度语义匹配 |
| `server/services/desktop/window_enum.py` | ~150 | PowerShell Win32 EnumWindows 窗口列表+光标位置 |

### Tier 3：指标 + 管理

| 文件 | 行数 | 功能 |
|------|------|------|
| `server/services/metrics.py` | ~80 | 内存P95/P50/平均延迟收集，240样本环形缓冲区 |

---

## 修改文件一览

| 文件 | 改动 |
|------|------|
| `server/config.py` | 移除OmniParser配置；添加8供应商独立配置 + 特性开关；修复 `.env` 加载路径 |
| `server/services/llm/__init__.py` | 导出providers.py新增函数 |
| `server/services/llm/client.py` | 保留 `call_deepseek()` 兼容签名 |
| `server/services/planning/router.py` | **核心重写**：`process_query()` 改为纯视觉LLM管道；新增 `_build_annotation_from_pointer()`、保留 `generate_steps()` 兼容 |
| `server/services/planning/__init__.py` | 更新导出 |
| `server/services/perception/__init__.py` | 添加 `serialize_elements` 导出 |
| `server/services/llm_ai.py` | 兼容层适配新架构 |
| `server/routes/demo.py` | 移除OmniParser引用；新增 `/evaluate`、`/cancel` 端点 |
| `server/routes/admin.py` | 新增 `/metrics`、`/session/status` 端点 |
| `server/requirements.txt` | 添加 `pytesseract`、`sentence-transformers`、`numpy` |
| `scripts/start_all.bat` | 移除OmniParser启动步骤 |
| `scripts/stop_all.bat` | 移除OmniParser端口清理 (:8002) |
| `server/tests/test_replanner.py` | 适配纯视觉LLM架构 |
| `server/tests/test_legacy.py` | 适配新mock数据格式 |

---

## 与 OpenGuider 架构对应

| OpenGuider (Node.js) | HAJIMI_UI (Python) |
|----------------------|---------------------|
| `src/ai/index.js` | `services/llm/providers.py` |
| `src/agent/planner-chain.js` + `executor-chain.js` | `services/agent/chains.py::plan_and_locate()` |
| `src/agent/evaluator-chain.js` | `services/agent/chains.py::evaluate_step()` |
| `src/agent/replanner-chain.js` | `services/agent/chains.py::replan_goal()` |
| `src/agent/task-orchestrator.js` | `services/agent/orchestrator.py` |
| `src/agent/schemas.js` (Zod) | `models/schemas.py` (Pydantic) |
| `src/session/session-manager.js` | `services/session/manager.py` |
| `src/validation/bounds-validator.js` | `services/validation/coords.py` |
| `src/agent/interaction-pipeline.js` | `services/validation/postprocess.py` |
| `src/perception/ocr-engine.js` | `services/perception/ocr_engine.py` |
| `src/context/embedding-matcher.js` | `services/context/embedding_matcher.py` |
| `src/context/context-analyzer.js` | `services/context/distiller.py` |
| `src/perception/window-enum.js` | `services/desktop/window_enum.py` |
| `src/performance-metrics.js` | `services/metrics.py` |

---

## 核心数据流

```
用户输入 "打开微信"
       │
       ▼
PyQt5 B端: 截图 (mss) → base64 PNG
       │
       ▼
POST /api/demo/process {query, image}
       │
       ▼
router.process_query():
  1. 红线检测 (redline_service)
  2. 意图分类 (SetFit)
  3. 截图缓存检查 (900ms TTL)
  4. orchestrator.process_query():
     a. [可选] OCR 提取屏幕文本
     b. [可选] 语境蒸馏 (纯文本LLM总结)
     c. plan_and_locate(): 截图+query → 视觉LLM 单次调用
        → {goal, steps[{title,instruction}], pointer:{x,y,label}}
     d. 坐标后处理 (跳变检测+边界裁剪)
     e. 构建 ProcessResponse
       │
       ▼
响应 → PyQt5 B端渲染覆盖层 (箭头+高亮框)
       │
       ▼
用户点"下一步":
  POST /api/demo/step {action:"advance", image}
       │
       ▼
  orchestrator.evaluate_step():
    截图 → 视觉LLM 判断步骤完成
    → done: advance → locate next step
    → blocked: replan
    → not_done: 重复指引
```

---

## 关键改进点

| 改进 | 之前 | 之后 |
|------|------|------|
| UI检测 | OmniParser (CPU 2-4分钟) | 多模态LLM直接看图 (~5-15秒) |
| LLM调用次数 | Plan + Locate 各一次 | Plan+Locate 组合单次调用 |
| LLM供应商 | 2个 (Qwen + DeepSeek) | 8个 (Claude/OpenAI/Gemini/Groq/OpenRouter/Ollama/Qwen/GLM) |
| 步骤验证 | 无 (盲目推进) | 视觉LLM评估每步是否完成 |
| 坐标漂移 | 无处理 | 跳变检测+历史平滑 |
| 错误恢复 | 无 | 自适应token递减重试 |
| 截图缓存 | 无 | 900ms TTL + SHA-256去重 |
| 性能监控 | 无 | P95/P50/平均延迟指标 |

---

## 配置

`.env` 关键配置项 (位于 `server/.env`)：

```env
LLM_PROVIDER=qwen                           # 默认供应商
LLM_MODEL=Qwen/Qwen3.6-35B-A3B             # 模型
LLM_BASE_URL=https://api.siliconflow.cn/v1  # API地址
LLM_API_KEY=sk-...                          # API密钥

# 特性开关
EVALUATOR_ENABLED=true                      # 步骤评估循环
ORCHESTRATOR_ENABLED=true                   # 智能编排
DISTILLATION_ENABLED=false                  # 语境蒸馏(需额外LLM调用)
OCR_ENABLED=false                           # 本地Tesseract OCR
SCREENSHOT_CACHE_ENABLED=true               # 截图缓存
```

---

## 启动方式

### Mock模式 (UI演示，无需API Key)
```bat
cd D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System\HAJIMI_UI
set HAJIMI_MOCK_ONLY=1
python main.py
```

### 完整模式
```bat
cd D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System\HAJIMI_UI
scripts\start_all.bat
```
只启动 A端(:8010) + B端(UI)，无OmniParser。

---

## 测试结果

```
47 passed (blueprint 9 + intent 5 + redline 18 + replanner 5 + legacy 11)
```
