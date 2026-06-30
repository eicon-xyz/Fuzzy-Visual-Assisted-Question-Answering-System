"""
HAJIMI Client — Day 2 验证脚本
=================================
验证 Day 2 交付物：Web 管理面板结构、审计代理联调准备、配置轮询器联调准备

用法::

    python client/day2_check.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_ADMIN = os.path.join(PROJECT_ROOT, "web-admin")
OK = 0
FAIL = 0


def check(label, condition, detail=""):
    global OK, FAIL
    if condition:
        print(f"  ✅ {label}")
        OK += 1
    else:
        print(f"  ❌ {label}  {detail}")
        FAIL += 1


# ═══════════════════════════════════════════════
#  1. Web 管理面板 — 目录结构
# ═══════════════════════════════════════════════
def test_web_admin_structure():
    print("=" * 50)
    print("  1. Web 管理面板 — 目录结构")
    print("=" * 50)

    check("web-admin/ 目录存在", os.path.isdir(WEB_ADMIN))
    check("  package.json", os.path.isfile(os.path.join(WEB_ADMIN, "package.json")))
    check("  vite.config.js", os.path.isfile(os.path.join(WEB_ADMIN, "vite.config.js")))
    check("  index.html", os.path.isfile(os.path.join(WEB_ADMIN, "index.html")))

    src = os.path.join(WEB_ADMIN, "src")
    check("  src/main.js", os.path.isfile(os.path.join(src, "main.js")))
    check("  src/App.vue", os.path.isfile(os.path.join(src, "App.vue")))
    check("  src/router/index.js", os.path.isfile(os.path.join(src, "router", "index.js")))
    check("  src/api/index.js", os.path.isfile(os.path.join(src, "api", "index.js")))

    views = os.path.join(src, "views")
    check("  src/views/Login.vue", os.path.isfile(os.path.join(views, "Login.vue")))
    check("  src/views/Dashboard.vue", os.path.isfile(os.path.join(views, "Dashboard.vue")))
    check("  src/views/Failures.vue", os.path.isfile(os.path.join(views, "Failures.vue")))
    check("  src/views/FlowMonitor.vue", os.path.isfile(os.path.join(views, "FlowMonitor.vue")))
    check("  src/views/SystemConfig.vue", os.path.isfile(os.path.join(views, "SystemConfig.vue")))
    check("  src/views/HealthMonitor.vue", os.path.isfile(os.path.join(views, "HealthMonitor.vue")))

    comps = os.path.join(src, "components")
    check("  src/components/AppLayout.vue", os.path.isfile(os.path.join(comps, "AppLayout.vue")))


# ═══════════════════════════════════════════════
#  2. Web 管理面板 — npm 依赖
# ═══════════════════════════════════════════════
def test_web_admin_deps():
    print()
    print("=" * 50)
    print("  2. Web 管理面板 — npm 依赖")
    print("=" * 50)

    node_modules = os.path.join(WEB_ADMIN, "node_modules")
    check("node_modules/ 已安装", os.path.isdir(node_modules),
          "运行 cd web-admin && npm install")

    if os.path.isdir(node_modules):
        packages = os.listdir(node_modules)
        required = ["vue", "vue-router", "element-plus", "echarts", "axios", "pinia"]
        for pkg in required:
            # npm 可能用嵌套目录，检查第一层
            found = any(d == pkg or d.startswith(pkg) for d in packages)
            check(f"  {pkg}", found)


# ═══════════════════════════════════════════════
#  3. Web 管理面板 — 核心文件内容
# ═══════════════════════════════════════════════
def test_web_admin_content():
    print()
    print("=" * 50)
    print("  3. Web 管理面板 — 关键内容")
    print("=" * 50)

    # 路由包含 6 个页面
    router_file = os.path.join(WEB_ADMIN, "src", "router", "index.js")
    if os.path.isfile(router_file):
        with open(router_file, "r", encoding="utf-8") as f:
            content = f.read()
        check("路由: /login", "/login" in content)
        check("路由: /dashboard", "dashboard" in content)
        check("路由: /failures", "failures" in content)
        check("路由: /flow", "/flow" in content or "Flow" in content)
        check("路由: /config", "'config'" in content or "/config" in content)
        check("路由: /health", "'health'" in content or "/health" in content)
        check("导航守卫 (noAuth)", "noAuth" in content)

    # Vite 代理配置
    vite_file = os.path.join(WEB_ADMIN, "vite.config.js")
    if os.path.isfile(vite_file):
        with open(vite_file, "r", encoding="utf-8") as f:
            content = f.read()
        check("API 代理到 localhost:8000", "localhost:8000" in content)

    # API axios 拦截器
    api_file = os.path.join(WEB_ADMIN, "src", "api", "index.js")
    if os.path.isfile(api_file):
        with open(api_file, "r", encoding="utf-8") as f:
            content = f.read()
        check("JWT Bearer 拦截", "Bearer" in content)
        check("401 自动跳转登录", "401" in content)


# ═══════════════════════════════════════════════
#  4. 审计代理 — 联调准备
# ═══════════════════════════════════════════════
def test_audit_integration():
    print()
    print("=" * 50)
    print("  4. 审计代理 — HTTP 上报联调准备")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent, desensitize_text

    # 测试请求体格式
    agent = AuditAgent()
    record = {
        "task_id": "550e8400-e29b-41d4-a716-446655440000",
        "query": "怎么安装微信",
        "intent_category": "operation_guide",
        "complexity_score": 35,
        "route": "L3",
        "total_steps": 3,
        "completed_steps": 3,
        "result": "success",
        "duration_ms": 45200,
        "feedback_type": "useful",
        "fingerprint_mismatches": 0,
        "redline_triggered": False,
        "timestamp": "2026-06-30T14:32:15+08:00",
    }
    agent.enqueue(record)

    # 检查队列
    depth = agent.get_queue_depth()
    check(f"记录入队成功 (depth={depth})", depth >= 1)

    # 检查 client_id 格式
    status = agent.get_queue_status()
    check(f"client_id 格式: {status['client_id'][:20]}...",
          status["client_id"].startswith("desktop-"))

    # 脱敏覆盖
    sensitive_tests = [
        ("密码=abc123", "REDACTED"),
        ("api_key=sk-secret", "REDACTED"),
        ("13800138000", "PHONE"),
        ("test@example.com", "EMAIL"),
        ("C:\\Users\\admin\\file.txt", "FILE_PATH"),
        ("身份证 110101199001011234", "ID_NUMBER"),
    ]
    for text, marker in sensitive_tests:
        result = desensitize_text(text)
        check(f"脱敏: {text[:25]} -> {marker}", marker in result)

    agent.shutdown()


# ═══════════════════════════════════════════════
#  5. 配置轮询器 — 联调准备
# ═══════════════════════════════════════════════
def test_config_integration():
    print()
    print("=" * 50)
    print("  5. 配置轮询器 — 联调准备")
    print("=" * 50)

    from client.config.config_poller import ConfigPoller

    poller = ConfigPoller(interval_min=5)

    # 基础状态
    state = poller.get_state()
    check("轮询器未启动 (running=False)", not state["running"])
    check(f"默认间隔 5min", state["interval_min"] == 5)
    check("last_etag 为空", state["last_etag"] == "")

    # 间隔范围
    poller.set_interval(3)
    check("间隔下限保护 (3→5)", poller.interval_min == 5)

    poller.set_interval(2000)
    check("间隔上限保护 (2000→1440)", poller.interval_min == 1440)

    poller.set_interval(30)
    check("正常间隔设置", poller.interval_min == 30)

    # 手动拉取（服务端未运行，预期返回 None）
    result = poller.poll_now()
    check("服务端不可达时返回 None", result is None,
          f"(预期 None，实际 {result})")

    poller.shutdown()


# ═══════════════════════════════════════════════
#  6. client/ 模块完整性
# ═══════════════════════════════════════════════
def test_client_modules():
    print()
    print("=" * 50)
    print("  6. client/ 模块完整性")
    print("=" * 50)

    client_dir = os.path.join(PROJECT_ROOT, "client")
    modules = {
        "voice/asr_client.py": "ASR 语音识别",
        "voice/tts_engine.py": "TTS 语音合成",
        "audit/audit_agent.py": "审计代理",
        "config/config_poller.py": "配置轮询器",
        "integration/controller.py": "B-C 集成控制器",
        "voice_setup.py": "Day 1 验证脚本",
        "list_devices.py": "设备列表工具",
        "requirements.txt": "依赖清单",
    }
    for path, desc in modules.items():
        full = os.path.join(client_dir, path)
        check(f"{desc} ({path})", os.path.isfile(full))


# ═══════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════
if __name__ == "__main__":
    print()
    print("  HAJIMI Day 2 — 验证")
    print()

    test_web_admin_structure()
    test_web_admin_deps()
    test_web_admin_content()
    test_audit_integration()
    test_config_integration()
    test_client_modules()

    print()
    print("=" * 50)
    print(f"  结果: {OK} 通过, {FAIL} 失败")
    print("=" * 50)
    if FAIL == 0:
        print("  Day 2 全部验证通过")
    else:
        print(f"  ⚠ {FAIL} 项未通过，请检查")
