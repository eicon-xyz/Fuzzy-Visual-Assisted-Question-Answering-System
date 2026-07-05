# HAJIMI 第二天工作进度 — 角色 A（后端/AI核心）

**姓名**：[请填写姓名]  
**学号**：[请填写学号]  
**日期**：2026年6月30日  
**角色**：A（后端 / AI核心）

---

## 一、完成任务

### 1. 意图理解服务 INTENT 完善 ✅

**文件**：`server/services/llm_ai.py`（`classify_intent` 方法扩展）

- 基于 jieba 分词 + 词性标注提取动词/名词组合
- 6 种意图域关键词规则覆盖：`operation_guide`（安装/下载/打开/设置…）、`element_cognition`（这是什么/那个…）、`error_diagnosis`（报错/失败/打不开…）、`ui_navigation`（返回/进入/切换…）、`file_management`（保存/另存为/导出…）、`emotion_comfort`（好烦/怎么办…）
- 综合置信度计算公式：`Conf = 0.4*P_intent + 0.4*P_referent + 0.2*P_context`
- 5 种指代消解策略框架：显式指代（"那个蓝色按钮"）、空间指代（"左边那个"）、鼠标指代（"这里"）、语义指代（"设置"）、上下文继承（连续对话）

### 2. 蓝图规划服务 PLANNER 初版 ✅

**文件**：`server/services/llm_ai.py`（`generate_steps` + `process_query` 方法）、`server/services/blueprint.py`

- **复杂度评分路由** `route(query) → L2/L3`：`score = 0.3*len(Q) + 8*n_verb + 10*cross_app`
  - L2（score < 30）：简单操作，规则模板匹配
  - L3（score ≥ 30）：复杂多步，调用 DeepSeek LLM 生成
- **L3 LLM 蓝图生成**：构造 Prompt（用户意图 + 约束）→ 调用 DeepSeek API → 解析返回的 Constant Steps
- **SCENARIO_ELEMENTS 模板库**：wechat/screenshot/default 三场景预定义 UI 元素坐标
- **步骤-元素绑定**（Demo 阶段机械循环）：`elements[i % len(elements)]`
- **蓝图状态机初版 4 路径**：`pending_confirm → executing → completed`、`executing → rolling_back → executing`、`executing → terminated`

### 3. LLM API 封装独立化 ✅

**文件**：`server/services/llm_ai.py`（`call_deepseek` 方法独立）

- DeepSeek API 统一调用入口：`call_deepseek(query, system_prompt=None, timeout=30)`
- 请求格式对齐 OpenAI Chat Completions API：`/v1/chat/completions`
- 超时保护（默认 30s）+ 异常捕获（返回 None 不崩溃）
- Mock fallback 机制：API Key 为空或调用失败时降级为场景预设数据
- `SYSTEM_PROMPT` 常量：定义 HAJIMI 角色（智能桌面指引助手）和输出格式要求
- 流式输出预留（`stream=True` 参数位）

### 4. OmniParser 客户端对接准备 ✅

**文件**：`server/services/omniparser_client.py`（新建）

- 封装本地 OmniParser V2 HTTP 调用：
  - `parse_screenshot(image_base64)` — 发送截图 → 返回 `List[UIElement]`
  - `parse_screenshot_full(image_base64)` — 返回元素列表 + SoM 标注图
- 默认地址 `http://127.0.0.1:9800/parse`
- 超时 120s（大图检测耗时较久）
- 配置项：`OMNIPARSER_URL`、`OMNIPARSER_TIMEOUT`
- 健康探测：`GET /probe/` → `device=cuda`/`device=cpu`

### 5. A-B 首次接口联调 ✅

**联调时间**：6月30日下午

与 B 端（潘振喆）完成首次 HTTP 接口联调：

- **健康检查**：B 启动时调用 `GET /api/demo/health` 确认 A 端在线，状态栏显示「A 端已连接」
- **核心流程** `/process`：B 通过 `mss` 截屏 → Base64 编码 → `POST /api/demo/process`（`{query, image}`）→ A 返回 `ProcessResponse`（含 steps + annotations）→ B 在桌面挂件显示步骤
- **步骤推进** `/step`：B 用户点击"下一步" → `POST /api/demo/step` → A 推进蓝图状态 → B 更新步骤高亮
- **约定**：Demo Key `hajimi-demo-2026`、响应格式统一 `ErrorResponse` 包装
- **坐标系约定**：bbox 以截图左上角为原点（与 B 的 mss 截图一致），单位=物理像素
- 联调脚本 `scripts/verify_integration.py` 自动化 health + process + step 流程

### 6. A-C 接口契约初次对齐 ✅

- 与 C 端（涂浚稷）确认审计端点和配置端点需求
- 约定 `POST /api/audit/report` 批量上报格式（`{client_id, batch: [...]}`）
- 约定 `GET /api/config/pull` 配置拉取（ETag 条件请求支持）
- C 端先独立开发语音模块，审计/配置端点 Day 3-4 实现

### 7. 环境配置修复 ✅

- `config.py` 修复 `load_dotenv()` 无路径问题：改为 `load_dotenv(Path(__file__).resolve().parent / ".env")`
- 从项目根目录启动 uvicorn 时正确读取 `server/.env`
- 端口统一为 8000（原计划 8001 被占用问题已解决）

---

## 二、目录结构（Day 2 增量）

```
server/
├── services/
│   ├── llm_ai.py               # 扩展：意图分类6域 + 蓝图生成 + DeepSeek封装
│   ├── blueprint.py            # 扩展：复杂度路由 + fingerprint比对
│   └── omniparser_client.py    # 新增：本地 OmniParser HTTP 客户端
├── scripts/（项目根）
│   ├── start_server.bat
│   ├── setup_server_env.bat
│   └── verify_integration.py   # 新增：A-B 联调验收脚本
```

---

## 三、验证结果

| 测试 | 项目 | 结果 |
|------|------|------|
| `/health` 端点 | 健康检查 | ✅ B 端可探测 |
| `/process` 端点 | B 传截图+query → 返回步骤 | ✅ 4 步微信安装 |
| `/step` 端点 | advance/rollback/skip/terminate | ✅ 状态迁移正确 |
| DeepSeek API | 真实 LLM 调用 | ✅ 生成步骤文案 |
| Mock Fallback | 无 API Key 场景 | ✅ 降级为预设数据 |
| 意图分类 | 6 域关键词规则 | ✅ 覆盖 6 种意图 |
| A-B 联调 | health + process + step | ✅ 全流程通过 |
| `verify_integration.py` | 自动化验收 | ✅ 无 FAIL |

**A-B 联调场景验证**：
```
1. B 启动 → health 探测 → 「A 端已连接」
2. 用户输入 "怎么安装微信" + 截图 → POST /process → 返回 4 步
3. B 桌面挂件展示步骤列表 + 覆盖层绘制红框
4. 点击"下一步" → POST /step advance → 步骤高亮更新
5. 全流程 < 10 秒
```

---

## 四、遗留问题

1. **UI 元素坐标仍是写死的 `SCENARIO_ELEMENTS` 模板**，与用户真实桌面无关 — 需 Day 3 对接 OmniParser 真实检测
2. **`Step.target_element_id` 从未被 LLM 填充** — 绑定为机械循环 `elements[i % len(elements)]`，语义匹配缺失
3. **LLM 生成步骤时看不到 UI 元素列表** — `call_deepseek()` 不接收 elements 参数，是 P0 级别瓶颈
4. **意图分类仅有 6 种 if-else 规则**，未覆盖 9 大意图域（缺少 `content_cognition`、`tutorial_generation`、`proactive_alert`）
5. **蓝图状态机缺少异常迁移路径**：`suspended → advance`（挂起恢复）、`executing → suspended`（外部挂起）、`timeout → suspended`
6. **B 端检验模式未对接** — B 期望 `/inspect` 端点用于元素全量检测（非任务模式）

---

## 五、下一步计划（Day 3）

- **P0 元素感知**：OmniParser 真实检测集成 → process 管线改造 → LLM Prompt 注入元素列表
- **P2 动态重规划**：`StepRequest` 增加 `image` 字段 → `/step` 重规划分支
- **P3 状态机补完**：蓝图状态机 7 状态全覆盖（suspended/rolling_back 异常路径）
- `/inspect` + `/relocate` 端点实现
- A-B 检验模式联调
- A-C 审计/配置端点实现
