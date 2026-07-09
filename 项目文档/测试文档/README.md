# HAJIMI 测试文档 — 使用说明

> V2.2 | 2026-07-07 | 基准：`启动本地.bat`

## 文档

| 文件 | 内容 |
|------|------|
| `00-大纲.md` | 测试覆盖矩阵 + 环境配置 |
| `01-HAJIMI测试方案.docx` | 7模块功能+UI测试用例（严格参照模板格式） |
| `02-HAJIMI单元测试报告.docx` | 7模块逐条测试结果 + 编码人/QA信息（严格参照模板格式） |

## 测试脚本

| 脚本 | 目标 | 需A端 | 说明 |
|------|------|-------|------|
| `test_new_jimi.py` | A端 HTTP端点 | ✅ | 测试 HAJIMI_UI/server/ 全部端点 |
| `test_hajimi_ui.py` | B端嵌入式A端 | ✅ | 测试 B端专属端点(inspect/step等) |
| `test_client_modules.py` | C端6模块 | ❌ | ASR/TTS/审计/配置/BC集成/AuditBuilder |
| `test_data_connectivity.py` | A-C数据回路 | ✅ | 审计回路+配置回路+BC链+12页验证 |
| `demo_connectivity.py` | 可视化演示 | ✅ | 逐步打印实际数据，直观展示数据流动 |

## 运行顺序

```bash
# 1. 启动 A端（二选一）
启动本地.bat                              # 一键
cd HAJIMI_UI && python -m uvicorn server.main:app --host 0.0.0.0 --port 8010  # 手动

# 2. C端模块测试（无需A端）
python 项目文档/测试文档/test_client_modules.py

# 3. A端端点测试
python 项目文档/测试文档/test_new_jimi.py

# 4. 数据连通性测试（核心）
python 项目文档/测试文档/test_data_connectivity.py

# 5. 可视化演示
python 项目文档/测试文档/demo_connectivity.py
```

## 目录速查

| 组件 | 路径 |
|------|------|
| A端 Server | `HAJIMI_UI/server/` |
| A端 数据库 | `HAJIMI_UI/server/data/hajimi.db` |
| B端 桌面 | `HAJIMI_UI/main.py` |
| B端 Core | `HAJIMI_UI/core/` |
| C端 Python | `client/` |
| C端 Web面板 | `web-admin/src/` |
