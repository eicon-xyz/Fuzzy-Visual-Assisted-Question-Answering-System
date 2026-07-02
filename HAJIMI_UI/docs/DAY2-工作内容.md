# HAJIMI 实训 DAY2 工作内容

> **日期**：实训第 2 天（对照 [`设计文档V2.md`](../设计文档V2.md)「准备阶段 1–2 天」）  
> **角色**：B 端（前端 / 桌面应用）  
> **成员分工依据**：设计文档 §九 — B 负责感知层 + 执行层（视觉）+ GUI  
> **文档版本**：1.0.0 · 2026-07-01

---

## 一、DAY2 目标（对照两周路线）

| 路线阶段 | 天数 | DAY2 对应里程碑 |
|----------|------|-----------------|
| **准备** | 1–2 天 | 环境跑通、OmniParser/LLM 试用、FastAPI 与 B 端首次联调 |
| 后续（预告） | 3–5 天 | 截图 → 解析 → SoM → LLM → 标注基础闭环 |

**DAY2 核心目标**：完成 **B ↔ A HTTP 契约对齐** 与 **B ↔ C 信号契约文档化**，并实现/验证「截图上传 → A 返回步骤与坐标 → B 屏幕标注」的最小闭环。

---

## 二、DAY2 任务清单

### 2.1 环境与工程（全员 · 准备阶段）

| # | 任务 | 负责 | 验收标准 | 状态 |
|---|------|------|----------|------|
| 1 | 克隆/打开 HAJIMI_UI 工作区，Python 3.10+ 可用 | B | `python --version` 正常 | ✅ |
| 2 | A 端：`scripts/setup_server_env.bat` 创建 `server/.venv` | A | health 200 | ✅ |
| 3 | 配置 `server/.env`（`DEEPSEEK_API_KEY`） | A | process 非 Mock 文案 | ✅ |
| 4 | B 端：`pip install` PyQt5、mss 等依赖 | B | `python main.py` 可启动 | ✅ |
| 5 | 约定 Demo Key 与端口（默认 `8010` / `hajimi-demo-2026`） | A+B | 双方 `config` 一致 | ✅ |

### 2.2 B 端开发任务（DAY2 当日）

| # | 任务 | 说明 | 涉及文件 | 状态 |
|---|------|------|----------|------|
| 1 | **API 客户端骨架** | 封装 health / process / step，统一 `X-Demo-Key` 与超时 | `core/api_client.py`, `config.py` | ✅ |
| 2 | **截图上传 process** | mss 截屏 → Base64 → `POST /api/demo/process` | `core/task_worker.py`, `core/screen_capture.py` | ✅ |
| 3 | **标注层对接** | 解析 A 返回 `steps[].annotation`，绘制红框/箭头 | `ui/overlay_anno.py`, `core/annotation_mapper.py` | ✅ |
| 4 | **health 启动探测** | 启动时显示「A 端已连接」或启动指引 | `ui/main_widget.py`, `api_client.get_api_status_message()` | ✅ |
| 5 | **联调脚本** | `scripts/verify_integration.py` 自动化 health + process + step | `scripts/verify_integration.py` | ✅ |
| 6 | **接口文档** | B 对 A/C 接口总结 + A 改动汇入 | `docs/B端接口总结-对A与对C_v2.md`（v2） | ✅ DAY3 升版 |
| 7 | **B–C 契约对齐** | 与 C 确认 9 个信号/共享状态（文档层） | `b-c-api-contract.md` | ✅ 已有 |
| 8 | **Mock 降级路径** | A 未启动时可本地演示 | `core/mock_backend.py`, `HAJIMI_MOCK_*` | ✅ |

### 2.3 A 端配合任务（DAY2 当日 · A 成员）

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 1 | FastAPI Demo 路由：`/health`, `/process`, `/step`, `/clarify`, `/report` | 对齐 `api-contract-demo.yaml` | ✅ |
| 2 | `/process` 接收 `image` 字段（初版可先 Mock bbox） | B 可传截图 | ✅（后续已升级为真实检测） |
| 3 | 返回 `task_id`, `steps`, `blueprint` | B 步骤 UI 可渲染 | ✅ |
| 4 | 启动脚本与 README | `scripts/start_server.bat`, `server/README_v2.md` | ✅ DAY3 升版 |

### 2.4 C 端任务（DAY2 · 可并行，不阻塞 B–A）

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 1 | 阅读 `b-c-api-contract.md` | 了解 B 将暴露的信号 | 📋 文档就绪 |
| 2 | 命令行验证 Vosk / pyttsx3 | C 独立开发，暂不依赖 B GUI | ⏳ C 自行推进 |
| 3 | 审计 SQLite 队列原型 | 为 Day 10–11 联调做准备 | ⏳ |

---

## 三、DAY2 交付物

| 交付物 | 路径 | 说明 |
|--------|------|------|
| B 端接口总结（对 A / 对 C） | `docs/B端接口总结-对A与对C_v2.md` | DAY3 升版；含系统设置与 auto health |
| Demo API 契约 | `api-contract-demo_v2.yaml` | v2 含 health 扩展；v1 见 `api-contract-demo.yaml` |
| B–C 接口契约 | `b-c-api-contract.md` | C 联调基准 |
| A 端改动记录 | `server/docs/CHANGELOG-A端_v2.md` | A 维护 |
| B 端改动记录 | `docs/CHANGELOG-B端_v2.md` | B 维护 |
| DAY3 工作总结 | `docs/DAY3-工作内容_v2.md` | GPU 兼容 + 系统设置 UI |
| 联调验收脚本 | `scripts/verify_integration.py` | 一键 health/process/step |
| 可运行 Demo | `python main.py` + A 端启动 | 输入问题 → 屏幕红框 |

---

## 四、DAY2 验收标准

### 4.1 必须通过

1. A 端 `GET /api/demo/health` → `{ "status": "ok" }`
2. B 端输入「怎么安装微信」→ 调用 A（或 Mock）→ 面板显示步骤列表
3. 覆盖层出现红框/箭头（Mock 或 A 返回坐标均可）
4. `python scripts/verify_integration.py` 无 FAIL（inspect 可 SKIP 小图）

### 4.2 DAY2 不要求（留给 DAY3+）

- 真实 OmniParser 检测（已在后续迭代完成）
- Native UI v2 全量对齐 HTML
- C 端语音联调
- `/relocate` 分步手动定位（DAY3+ 已完成）
- 检验模式全量框选（DAY3+ 已完成）

---

## 五、DAY2 实际进度说明（至 2026-06-30）

项目已超出 DAY2 基线，以下能力在 DAY2 之后完成，**写入 DAY2 文档便于实训报告对照**：

| 能力 | 完成日期 | 简述 |
|------|----------|------|
| 真实视觉检测 + `/inspect` | 2026-06-29 | A：OmniParser；B：检验模式 UI |
| HiDPI 坐标修复 | 2026-06-30 | `core/overlay_coords.py` |
| 分步手动定位 `/relocate` | 2026-06-30 | PrepareStep + 重截图 |
| 本地 OmniParser + health 预检 | 2026-06-30 | `omniparser_ready`、360s 超时 |
| Native UI v2 | 2026-06-30 | `ui/native/` 对照 HTML 设计 |

> **DAY2 报告建议写法**：DAY2 完成「契约对齐 + 最小联调闭环」；上表能力可放在「DAY3–5 延伸」或附录。

---

## 六、DAY3 计划（预览）

> **已完成**：详见 [`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md)

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 真实截图 + OmniParser 检测验收 | 红框与桌面元素人工对齐 |
| P0 | 检验模式稳定化 | 预检、超时、防重复点击 |
| P1 | `/clarify` UI 接入 | 低置信度澄清对话 |
| P1 | `/step` 指纹校验与挂起 UI | 蓝图状态机完整体验 |
| P2 | C 端 ASR 信号接入控制栏 | 按 `b-c-api-contract.md` 联调 |
| P2 | 红线检测模块接入提问前拦截 | 设计文档 §4.2.4 |

---

## 七、DAY2 工作日志模板（提交实训用）

```markdown
### 日期：____年__月__日（DAY2）

**今日完成**
- 
- 

**遇到的问题与解决**
- 

**与 A / C 联调情况**
- A 端：
- C 端：

**明日计划（DAY3）**
- 

**截图/录屏**（可选）
- 主界面 + 红框标注
- verify_integration 终端输出
```

---

## 八、快速命令参考

```powershell
# 1. 启动 A 端（server/.venv）
scripts\start_server.bat

# 2. 健康检查
curl http://127.0.0.1:8010/api/demo/health

# 3. 联调脚本
python scripts\verify_integration.py

# 4. 启动 B 端
python main.py

# 5. 全栈（OmniParser + A + 说明）
scripts\start_all.bat
```

---

## 九、学校 GPU 容器部署 OmniParser（可选）

若本地 Windows CPU 推理过慢，可在学校 **A800 GPU 容器**内按已验证环境部署 OmniParser，供 A 端远程调用或团队共享检测服务。

| 步骤 | 文档 |
|------|------|
| 连接 Jupyter / VSCode / SSH | [`校园GPU与OmniParser环境速查_v2.md`](校园GPU与OmniParser环境速查_v2.md) §一 |
| 验证 `nvidia-smi` / 显存占用 | 同上 §二 |
| 安装 OmniParser v2（严格版本 + 4 处源码修改） | 同上 §三；细节见 [`OmniParser GPU 环境交接文档.md`](../OmniParser%20GPU%20环境交接文档.md) |
| 与 HAJIMI A 端对接 | [`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md) §3.3.7；A 端 runbook：[`A端-学校GPU部署与联调指南_v2.md`](../server/docs/A端-学校GPU部署与联调指南_v2.md) |

---

## 十、参考文档

- 团队分工：[`设计文档V2.md`](../设计文档V2.md) §九
- B 接口总结 v2：[`B端接口总结-对A与对C_v2.md`](B端接口总结-对A与对C_v2.md)
- DAY3 工作总结 v2：[`DAY3-工作内容_v2.md`](DAY3-工作内容_v2.md)
- 校园 GPU / OmniParser 速查 v2：[`校园GPU与OmniParser环境速查_v2.md`](校园GPU与OmniParser环境速查_v2.md)
- 开发路线：[`设计文档V2.md`](../设计文档V2.md) §十
