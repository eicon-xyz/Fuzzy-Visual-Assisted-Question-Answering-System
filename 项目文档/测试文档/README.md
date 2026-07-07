# HAJIMI 测试文档 — 使用说明

> V2.2 | 2026-07-07 | A+B+C 三端

## 文档

| 文件 | 内容 |
|------|------|
| `00-大纲.md` | 测试覆盖矩阵 + 环境配置 |
| `01-HAJIMI测试方案.docx` | 8模块56条测试用例（A端23 + B端9 + C端18 + 系统6） |
| `02-HAJIMI单元测试报告.docx` | 8模块逐条结果 + 汇总表（56/56通过） |

## 测试脚本

| 脚本 | 目标 | 需A端 | 说明 |
|------|------|-------|------|
| `test_new_jimi.py` | A端独立服务器 | ✅ | new_JIMI/HAJIMI_UI/server/ |
| `test_hajimi_ui.py` | B端嵌入式服务器 | ✅ | HAJIMI_UI/server/ |
| `test_client_modules.py` | A+B+C 客户端模块 | ❌ | ASR/TTS/审计/配置/BC集成/AuditBuilder |

## 运行

```bash
# 1. 模块测试（无需A端）
python 项目文档/测试文档/test_client_modules.py

# 2. 启动A端
cd new_JIMI/HAJIMI_UI
python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

# 3. A端测试
python 项目文档/测试文档/test_new_jimi.py

# 4. B端嵌入式测试（先停上面A端，再启HAJIMI_UI的A端）
python 项目文档/测试文档/test_hajimi_ui.py
```

## 两个 A 端的区别

| 特征 | new_JIMI | HAJIMI_UI |
|------|----------|-----------|
| 端点 | 27 | 31 |
| 独有 | metrics, session/status | inspect, step, relocate, locate, clarify, report, health/live |
| 定位 | A端独立开发 | B端内嵌A端 |
