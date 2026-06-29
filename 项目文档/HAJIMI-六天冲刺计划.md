# HAJIMI 六天冲刺计划

> **团队**：A（后端/AI）、B（前端/桌面）、C（集成/语音/管理端）  
> **周期**：6 天  
> **目标**：完成 Demo 阶段全流程闭环 —— 「语音/文本提问 → 屏幕感知 → 意图理解 → 蓝图规划 → 多模态指引执行 → 审计上报」  
> **每日制度**：09:00 站会（15min）→ 开发 → 17:30 进度同步（15min）

---

## 依赖关系速查

```
A: FastAPI框架 ──→ DB Schema ──→ 意图理解API ──→ 蓝图规划API
                    │                              │
                    └──────────────┬───────────────┘
                                   ▼
C: 语音模块(独立) ──→ 审计代理(需A的API) ──→ 配置拉取 ──→ Web管理面板(需A的API)
        │
        └──→ 需B的GUI信号接口(第3天联调)
        
B: 屏幕捕获 ──→ UI解析器 ──→ SoM标注 ──→ 桌面挂件GUI ──→ 屏幕覆盖层
        │                                            │
        └────────────────────────────────────────────┘
                    全部需A的API(第2天起可用Mock)
```

---

## 第一天：环境搭建 + 核心骨架

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 全员站会：确认依赖、风险、当日目标 |
| **09:15–12:00** | **FastAPI 项目初始化**：`pip install fastapi uvicorn sqlalchemy alembic`，创建项目目录结构（`server/api/`、`server/models/`、`server/services/`），编写 `/api/health` 端点并跑通 Uvicorn | **PyQt5 骨架窗口**：`pip install pyqt5 mss pillow opencv-python`，创建 `main.py` 调通 `QApplication`，验证透明窗口属性（`FramelessWindowHint` + `WA_TranslucentBackground`），跑通一个空白毛玻璃窗口 | **语音环境搭建**：`pip install SpeechRecognition pyttsx3 vosk`，下载 Vosk 中文小模型（`vosk-model-small-cn-0.22`，~50MB），写 `voice_setup.py` 验证麦克风可录音、扬声器可播放 TTS 测试句 |
| **12:00–13:30** | 午休 |
| **13:30–15:30** | **数据库 Schema 设计**：用 SQLAlchemy 定义 7 张表 ORM 模型（User / Transaction / StepLog / Template / Feedback / Failure / SystemConfig），生成 Alembic 初始 Migration，`alembic upgrade head` 建表到本地 SQLite | **屏幕捕获模块 CAP**：`mss` 截取全屏 → `PIL.Image` 转 PNG bytes → 验证 DPI 缩放（`awareness` 参数）。输出：`capture.py`，函数 `capture_screen() -> bytes` | **ASR 模块**：封装 `asr_client.py`：`start_recording()` / `stop_and_transcribe()`。Vosk 离线优先，麦克风输入 → WAV → Vosk 识别 → 返回文字。用 CLI 脚本自测："你好世界" → "你好世界" |
| **15:30–17:30** | **核心 API 骨架**：按 `api-contract-demo.yaml` 创建 5 个路由文件（`health.py` / `process.py` / `step.py` / `clarify.py` / `report.py`），每个返回 Mock JSON（硬编码示例数据），用 Swagger UI 验证 | **UI 解析器 PARSER 环境**：安装 OmniParser V2（或备选 PaddleOCR + GroundingDINO），验证 GPU 可用。对一张本地截图跑通 `parse_ui(image) -> [{bbox, type, text}]` | **TTS 模块**：封装 `tts_engine.py`：`enqueue(text, priority)` → FIFO 队列 → `pyttsx3` 播放。线程安全（`threading.Lock`）。自测 3 条文本连续排队播报 |
| **17:30–17:45** | 同步：各人汇报进度 + 阻塞项 |

**第一天交付物**：
- A：FastAPI 运行在 `localhost:8000`，Swagger UI 可见 5 个端点返回 Mock 数据，SQLite 7 表建完
- B：PyQt5 空白毛玻璃窗口可显示，截图函数可返回 bytes，OmniParser 环境可用
- C：命令行可录音转文字、可 TTS 播报

---

## 第二天：模块核心逻辑

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 站会 |
| **09:15–12:00** | **意图理解服务 INTENT**：实现 `intent_service.py`：① `jieba` 分词 + 词性标注 → 提取动词+名词 ② 微调后的 `BERT-base-chinese` 九大意图域分类 ③ 5 种指代消解策略框架（显式/空间/鼠标/语义/上下文） ④ 综合置信度计算公式。接 `/api/demo/process` 接收 query → 返回 intent JSON | **SoM 标注生成 SOM**：输入 PARSER 的元素列表 + 截图 → OpenCV 绘制彩色边界框 + `~N` 标签 → 输出 `annotated_image` bytes + `Map{~N: {bbox, center}}`。自测：对截图生成标注图，肉眼确认编号清晰 | **审计代理 AuditAgent**：创建 `audit_agent.py`：① 本地 SQLite `audit_queue` 表（WAL 模式）② `enqueue(AuditRecord)` 写入方法 ③ 隐私脱敏函数（窗口标题正则替换、文件路径仅保留扩展名、密码字段 → `[REDACTED]`）④ 批量上报触发器（累积 10 条或 5 分钟） |
| **12:00–13:30** | 午休 |
| **13:30–15:30** | **蓝图规划服务 PLANNER**：实现 `planner_service.py`：① 复杂度评分路由 `route(query) -> L2/L3`（`score = 0.3*len + 8*n_verb + 10*cross`）② L3：构造 LLM Prompt（SoM 图 + 意图 + 约束）→ 调用 GPT-4V API → 解析返回的 Constant Steps ③ 蓝图状态机骨架（7 状态 + 指纹比对逻辑 `Jaccard >= 0.8`）。接 `/api/demo/step` → `advance/rollback/skip/terminate` | **桌面挂件主 UI（上）**：用 PyQt5 实现三栏布局骨架：① 左侧 5 按钮列（QPushButton + QSS 样式）② 中栏对话区（QScrollArea + 聊天气泡 QLabel）③ 右侧详情面板（QWidget 可滑出）。信号槽框架：定义 `asr_start/stop`、`tts_enqueue`、`audit_submit` 等 PyQt Signal | **配置拉取 ConfigPoller**：实现 `config_poller.py`：① 定时器（默认 30min）轮询 `GET /api/config/pull` ② 支持 ETag 条件请求 ③ 检测到新版本 → emit `config_updated` 信号。自测：对 A 的 Mock 端点定时拉取 |
| **15:30–17:30** | **LLM API 封装**：`llm_client.py`：GPT-4V / Qwen-VL-Max 统一适配层（API Key 配置、请求重试、超时 30s、流式输出预留）。自测：发送一张截图 + "这是谁的桌面？" → 验证响应 | **桌面挂件主 UI（下）**：③ 步骤卡片列表（步骤序号 + 动作描述 + 状态色标）④ 底部输入栏（QLineEdit + 发送按钮 + 麦克风按钮）⑤ 状态指示器（就绪/解析中/执行中/挂起）+ 执行控制栏（上一步/下一步按钮）。QSS 毛玻璃效果（`rgba + backdrop-blur` 模拟） | **Web 管理面板（上）**：Vue3 + Element-Plus 脚手架初始化（`npm create vue@latest`）。搭建左侧导航 + 路由框架（5 页面占位）。实现登录页（居中卡片 + JWT 登录逻辑）和总览页骨架（5 个 KPI 卡片 + 2 饼图区域 + 2 折线图区域，ECharts 引入但暂用静态数据） |
| **17:30–17:45** | 同步 |

**第二天交付物**：
- A：`POST /api/demo/process` 可接收 query + image → 返回完整 ProcessResponse；`POST /api/demo/step` 可推进/回退步骤
- B：桌面挂件三栏布局可见，按钮可点击切换面板，信号槽框架定义完成
- C：审计代理可写入本地 SQLite 并触发批量上报；Web 面板登录页 + 总览骨架渲染

---

## 第三天：打通第一条端到端链路

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 站会（重点：B 与 C 的语音信号联调、A 与 B 的 /process 联调） |
| **09:15–12:00** | **服务端 API 扩展**：扩展 Server API：① 配置热部署接口 `/api/admin/config/current` + `/api/admin/config/deploy` ② 审计日志批量接收 `/api/audit/report` + 反馈 `/api/audit/feedback` ③ 管理员统计接口。自测：Postman 批量发包验证 | **屏幕覆盖层 ANNO**：全屏 `QWidget` 透明窗口（`StaysOnTopHint + Tool + WA_TransparentForMouseEvents`）：① `draw_arrow(from, to)` 红色箭头 ② `draw_highlight(bbox)` 红色虚线框 ③ `draw_label(pos, text)` 白底红字编号标签。与 SoM 坐标联动自测 | **B-C 语音信号联调**：上午与 B 对接 PyQt5 信号接口：① 绑定 B 的 `mic_button.pressed/released` → C 的 `asr_start/stop` ② 绑定 C 的 `asr_result` → B 的输入框 ③ 绑定 B 的 `tts_enqueue` → C 的 TTS 队列。联调测试：按下 B 的麦克风按钮 → C 录音转文字 → B 输入框出现文字 |
| **12:00–13:30** | 午休 |
| **13:30–15:30** | **A-B 联调 /process**：B 调用 `POST /api/demo/process`（传截图 + 用户问题）→ A 返回 steps + annotations → B 在挂件显示步骤 + 在覆盖层绘制标注。联调验证：全过程 < 10 秒 | **A-B 联调 /step**：B 用户点"下一步" → 调用 `POST /api/demo/step` → A 推进蓝图 → B 更新步骤高亮 + 覆盖层标注。联调验证步骤推进 + 挂起（模拟指纹不匹配） | **审计代理 HTTP 上报**：对接 A 的 `POST /api/audit/report`。C 模拟 B 发射 `audit_submit` 信号 → AuditAgent 接收 → 脱敏 → 写入本地 SQLite → 批量 POST。验证：断网情况下队列积压 + 联网后自动补传 |
| **15:30–17:30** | **主动澄清逻辑**：完成 `/api/demo/clarify` 端点的真实逻辑（不再 Mock）。综合置信度 < 80% → 生成探测性问题（二选一）→ 用户回答 → 追加锚点 → 更新意图 | **挂件完成度打磨**：步骤状态动画（completed 灰色+绿勾 / active 蓝色高亮 / pending 半透明）、TTS 声波动画（喇叭图标 CSS animation）、对话区自动滚动到底部、输入框 focus 快捷键 | **Web 管理面板（中）**：实现失败归因页：① 失败类型柱状图（ECharts）② 失败趋势折线图 ③ 失败列表（Element-Plus Table + 分页）④ 右侧详情滑出面板（含 LLM 快照折叠区）。对接 A 的 `/api/admin/failures/*` 端点（若 A 尚未就绪则继续 Mock） |
| **17:30–17:45** | 同步 |

**第三天交付物**：
- 端到端链路打通：用户提问（文本或语音） → 屏幕感知 → 意图理解 → 蓝图规划 → 屏幕标注 + TTS 播报
- B-C 语音信号全部联调通过
- C 的审计代理可批量上报到 A

---

## 第四天：功能完善 + 全场景覆盖

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 站会 |
| **09:15–12:00** | **红线检测模块**：`redline_service.py`：关键词规则 + 正则（自动点击/抢票/扫描硬盘/系统命令注入等）。检测到 → 返回标准拒答话术，不进入意图理解。接入 `/api/demo/process` 的最前端（在意图理解之前执行） | **L2 快路径实现**：不依赖 LLM，走本地规则：① OCR 识别（PaddleOCR 轻量版）② 元素匹配（关键词+类型）→ 生成简易步骤。自测：简单指令（"打开记事本"）< 3 秒返回 | **Web 管理面板（下）**：实现数据流监控页：① 桑基图/流向图（ECharts Graph）② 接口 QPS+成功率双轴图 ③ 客户端版本饼图。实现系统配置页：① 10 项表单（滑块/文本框/下拉）② JSON 编辑器（路由规则 TextArea + 格式化/校验按钮）③ 热部署二次确认弹窗。实现健康监控页：① 资源卡片 ② 组件状态指示灯 ③ 告警列表 |
| **12:00–13:30** | 午休 |
| **13:30–15:30** | **数据库查询优化**：为高频查询添加索引（`task_id`、`timestamp`、`intent_category`）；编写 admin stats 视图/查询（总览 KPI、趋势聚合、TOP N）；实现 `/api/admin/stats/*` 系列端点 | **适老增强模块**：实现大字模式（`font-size + 4px` 全局缩放）、慢语速默认值（`tts_speed = 0.85`）、一步一确认模式（每个步骤完成后等待用户手动确认才推进）。与 C 的语音设置联动 | **Admin API 全面对接**：管理面板全部图表从前端 Mock 数据切换为真实 API 调用。对接 A 的全部 `/api/admin/*` 端点（stats/top-tasks/redline/failures/flow/monitor/config）。端到端验证：管理面板修改配置 → 热部署 → B 的挂件配置更新 |
| **15:30–17:30** | **错误处理 + 日志**：统一异常中间件（`try/except` → 标准 ErrorResponse JSON）；结构化日志（`structlog`，含 `task_id` 追踪）；各端点边界条件测试（空 query、超长截图、无效 task_id） | **挂件折叠/最小化/拖拽**：① 折叠为圆形气泡（52px）② 最小化为按钮列（仅 54px 宽）③ 标题栏拖拽移动 ④ 右下角 resize 手柄 ⑤ 置顶切换。全部状态切换动画平滑 | **管理面板管理员功能**：JWT 刷新 Token 机制（2h access + 7d refresh）；告警标记已读/全部已读；CSV 导出（失败记录异步生成下载链接）；配置热部署操作日志 |
| **17:30–17:45** | 同步 |

**第四天交付物**：
- 红线检测生效，非法请求被拒
- L2 快路径可用（< 3s）
- Web 管理面板 5 个页面全部完成，图表对接真实数据
- 挂件交互完整（折叠/拖拽/置顶/resize）

---

## 第五天：全流程集成测试

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 站会（分工：A 主导端到端测试用例执行，B/C 配合排查） |
| **09:15–12:00** | **集成测试 — 核心 Happy Path**：按照联调检查清单逐条验证：① 文本提问 → 返回步骤+标注 ② 语音提问 → ASR → 同① ③ 逐步推进 → 标注更新 ④ 完成 → 审计上报 ⑤ 确认数据库记录写入 | **集成测试 — 异常路径**：⑥ 红线拦截（输入"帮我抢票"）→ 拒绝 ⑦ 置信度低 → 澄清弹窗 → 回答 → 更新意图 ⑧ 指纹不匹配 → 挂起 → 跳过/回退/终止 ⑨ 断网场景 → 审计队列积压 → 联网补传 | **集成测试 — 管理面板路径**：⑩ 登录 → Dashboard 数据正确 ⑪ 失败归因下钻（点击柱状图 → 列表过滤）⑫ 数据流拓扑图数据实时 ⑬ 配置修改 → 热部署 → 客户端配置更新 |
| **12:00–13:30** | 午休 + 全员 Bug 集中讨论 |
| **13:30–15:30** | **Bug 修复冲刺（按优先级）**：全员集中修复上午发现的 Bug。Priority: P0（阻塞核心流程）> P1（功能缺陷）> P2（体验问题） | 同 A | 同 A |
| **15:30–17:30** | **性能基准测试**：① `/api/demo/process` P99 延迟（不含 LLM）② LLM 调用 P95 延迟 ③ L2 路径端到端 < 3s ④ L3 路径端到端 < 10s ⑤ 截图+标注 单帧渲染 < 200ms ⑥ 内存占用（挂件 + 覆盖层） | 同 A | **管理面板性能**：① Dashboard 首次加载时间 ② 图表渲染帧率 ③ 失败列表无限滚动流畅度 ④ CSV 导出生成速度 |
| **17:30–17:45** | 同步：Bug 清单 + 性能数据汇总 |

**第五天交付物**：
- 集成测试报告（通过/失败/阻塞清单）
- Bug 列表（含优先级）
- 性能基准数据

---

## 第六天： Bug 清零 + 文档 + 演示准备

| 时段 | A | B | C |
|------|---|---|---|
| **09:00–09:15** | 站会：确认剩余 Bug 分工 |
| **09:15–12:00** | **P0/P1 Bug 清零**：昨日遗留阻塞项优先修复 | **UI 细节打磨**：① 窗口阴影 + 圆角微调 ② 颜色/字体一致性 ③ 步骤切换动画（`QPropertyAnimation`）④ 麦克风波形动画 ⑤ 喇叭声波动画 | **数据填充 + 演示场景准备**：① 预置 3 个演示用例（软件安装 L3 / 文档保存 L2 / 红线拦截）② 数据库灌入模拟历史数据（100+ 事务、20+ 失败）③ Web 面板截图准备 |
| **12:00–13:30** | 午休 |
| **13:30–15:30** | **文档完善**：① 更新 API 合约文档至最终状态 ② 补充架构图中的变更 ③ 写 `DEVELOPMENT.md`（环境搭建 + 启动步骤 + 常见问题） | **PyInstaller 打包验证**：① 配置 `.spec` 文件（包含 Vosk 模型、OmniParser 权重路径）② 执行 `pyinstaller hajimi.spec` ③ 验证生成的 exe 可在裸机（无 Python 环境）上启动 | **联调文档 + 演示脚本**：① 编写 Demo 演示脚本（按"安装微信"场景，精确到每一步的点击/等待/预期结果）② 录制演示操作步骤清单 ③ 准备项目 README 更新 |
| **15:30–17:00** | **全员最终验收**：按演示脚本完整走一遍全部场景，记录所有问题 | 同 A | **全员最终验收 + 管理面板操作演示**：管理员登录 → Dashboard → 失败归因下钻 → 数据流拓扑 → 配置热部署 → 健康监控 |
| **17:00–17:30** | **项目复盘**：① 完成度总结（计划 vs 实际）② 遗留问题清单 ③ 下次迭代优先级建议 | 同 A | 同 A |

**第六天交付物**：
- 可演示的完整 Demo（挂件 exe + Server + 管理面板）
- 更新后的技术文档
- 演示脚本
- 遗留问题清单 + 下次迭代计划

---

## 每日时间分配汇总

| 成员 | Day 1 | Day 2 | Day 3 | Day 4 | Day 5 | Day 6 |
|------|-------|-------|-------|-------|-------|-------|
| **A** | 框架+DB | 意图+蓝图+LLM | 服务端API+联调+澄清 | 红线+查询+错误处理 | 测试+Bug修复+性能 | Bug清零+文档+验收 |
| **B** | GUI骨架+截图+解析器 | SoM+挂件UI | 覆盖层+联调 | L2+适老+交互 | 测试+Bug修复 | UI打磨+打包+验收 |
| **C** | 语音环境+ASR+TTS | 审计+配置+Web骨架 | B-C联调+审计上报+Web中 | Web下+Admin对接 | 测试+Bug修复 | 数据+演示+复盘 |

## 关键风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| OmniParser V2 GPU 资源不足 | 中 | B 阻塞 | Day 1 即验证，若不通过立即切换 PaddleOCR 备选方案 |
| GPT-4V API 限流/延迟高 | 中 | A/B 阻塞 | 预置 3 个 Mock 蓝图作为降级方案，L2 路径完全离线可用 |
| PyQt5 透明窗口跨平台兼容 | 低 | B 延迟 | Day 1 验证 Windows 11 环境；已知 macOS 有 `WA_TranslucentBackground` 限制 |
| Vosk 中文模型准确率不达标 | 低 | C 延迟 | 同时集成 Google 在线 API 作为降级，离线兜底仅用于隐私优先场景 |
| 三人开发节奏不同步 | 中 | 联调阻塞 | 每天 2 次同步 + A 的 Mock API 从 Day 1 就位，B/C 不等待 A |

---

## 接口 Mock 就位时间线

| 接口 | Mock 就位 | 真实逻辑就位 | 消费者 |
|------|-----------|-------------|--------|
| `GET /api/health` | Day 1 AM | Day 1 AM | C（心跳） |
| `POST /api/demo/process` | Day 1 PM | Day 2 PM | B（核心流程） |
| `POST /api/demo/step` | Day 1 PM | Day 2 PM | B（步骤推进） |
| `POST /api/demo/clarify` | Day 1 PM | Day 3 PM | B（主动澄清） |
| `POST /api/demo/report` | Day 1 PM | Day 3 PM | C（审计上报） |
| `GET /api/config/pull` | Day 2 AM | Day 4 PM | C（配置拉取） |
| `GET /api/admin/*` | Day 3 PM | Day 4 PM | C（管理面板） |
| B-C Qt 信号接口 | Day 1 PM（定义） | Day 3 AM（联调） | B ↔ C |

---

## 每日站会模板

```
1. 昨天完成了什么？（每人 30 秒）
2. 今天计划做什么？（每人 30 秒）
3. 有什么阻塞？（需具体说明阻塞方 + 预计影响时长）
4. 需要谁配合？（明确对接人和时间窗口）
```

## 验收标准（Day 6 最终检查）

- [ ] 文本提问 "怎么安装微信？" → 屏幕出现标注 → 步骤列表显示 → TTS 播报 → 逐步完成
- [ ] 语音提问 "怎么保存文档？" → 同上有指引
- [ ] 输入 "帮我自动抢票" → 红线拦截，显示安全提示
- [ ] 执行中模拟指纹不匹配 → 挂起弹窗 → 选择"跳过"/"回退"/"终止"
- [ ] 任务完成 → 审计日志出现在管理面板
- [ ] 管理面板登录 → Dashboard 数据正确 → 失败归因可下钻 → 修改配置 → 热部署生效
- [ ] 挂件可拖拽/折叠/展开/调整大小/置顶
- [ ] 断网场景：审计队列积压，联网后自动补传
