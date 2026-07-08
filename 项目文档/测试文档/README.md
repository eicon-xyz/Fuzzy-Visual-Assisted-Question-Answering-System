# HAJIMI 测试文档 — 使用说明

> V2.2 | 2026-07-07 | A+B+C 三端

## 测试脚本

| 脚本 | 目标 | 需A端 | 说明 |
|------|------|-------|------|
| `test_client_modules.py` | A+B+C 客户端模块 | ❌ | ASR/TTS/审计/配置/BC集成/AuditBuilder |
| `test_new_jimi.py` | A端独立服务器 27端点 | ✅ | new_JIMI/HAJIMI_UI/server/ |
| `test_hajimi_ui.py` | B端嵌入式服务器 31端点 | ✅ | HAJIMI_UI/server/ |
| `test_data_connectivity.py` | **C<->A<->B 数据连通性** | ✅ | 审计回路/配置回路/BC审计链/Web认证/12页面数据可读 |

## C端 Web 面板真实数据模式

Web 面板已加入 `autoDetectServer()`：页面加载时自动探测 `:8010/api/demo/health`。A端在线则自动切换到真实数据，不再使用 Demo Mock。

验证：启动 A端 + Web面板 → Dashboard 显示的是数据库真实统计数据。

## 运行顺序

```bash
# 1. 模块测试（无需A端）
python 项目文档/测试文档/test_client_modules.py

# 2. 启动A端
cd new_JIMI/HAJIMI_UI
python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

# 3. A端端点测试
python 项目文档/测试文档/test_new_jimi.py

# 4. C<->A<->B 数据连通性测试（核心）
python 项目文档/测试文档/test_data_connectivity.py

# 5. Web面板验证
cd web-admin && npm run dev
# 浏览器 http://localhost:5173 → 总览应显示真实KPI数据

# 6. B端嵌入式测试（先停A端，换HAJIMI_UI再启）
python 项目文档/测试文档/test_hajimi_ui.py
```

## 数据连通性测试验证的回路

| 回路 | 路径 |
|------|------|
| 审计回路 | C审计代理→POST /audit/report→A DB→GET /admin/stats→C Web面板可查 |
| 配置回路 | C Web面板→POST /admin/config/deploy→A DB→GET /config/pull→C ConfigPoller |
| BC审计链 | B AuditRecordBuilder→C AuditAgent脱敏入队→批量POST→A入库→Web可查 |
| Web认证 | Login→JWT→Admin访问→无Key被拒 |
| 12页面 | 全部 /api/admin/* 端点通过AH读取真实数据 |
