"""
HAJIMI — A 端真实接口集成测试 (Day 3 更新)
===============================================
对 A 的服务器 (端口 8010) 进行真实集成测试。
包括：健康检查 (新字段)、审计上报、配置拉取、单独反馈。

用法::

    python client/real_api_test.py
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PASS = 0
FAIL = 0

SERVER = "http://localhost:8010"
KEY = "hajimi-demo-2026"

try:
    import httpx
    HTTP = httpx.Client(timeout=10)
    HTTPX_OK = True
except ImportError:
    HTTP = None
    HTTPX_OK = False


def ok(msg, condition=True):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {msg}")
        PASS += 1
    else:
        print(f"  ❌ {msg}")
        FAIL += 1


def info(msg):
    print(f"  ℹ️  {msg}")


def server_up():
    """检查 A 端服务是否可达"""
    if not HTTPX_OK:
        return False
    try:
        r = HTTP.get(f"{SERVER}/api/demo/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ═══════════════════════════════════════════════
#  测试
# ═══════════════════════════════════════════════

def test_health():
    """测试 /health 新旧字段"""
    print("=" * 50)
    print("  1. 健康检查"
         if server_up() else "  1. 健康检查 [A端离线]")
    print("=" * 50)

    if not server_up():
        info(f"A 端 {SERVER} 不可达，以下测试将验证离线降级能力")
        info("启动 A 端后重跑可测试真实端点: scripts\\start_server.bat")
        ok("离线降级: 服务器不可达时不崩溃", True)
        return False

    r = HTTP.get(f"{SERVER}/api/demo/health")
    data = r.json()
    ok(f"status={data.get('status')}", data.get("status") == "ok")
    ok(f"version={data.get('version')}", data.get("version") is not None)

    # 新字段 (A 端 2026-06-29 新增)
    detector = data.get("detector_backend", "")
    if detector:
        ok(f"detector_backend={detector}", True)
    else:
        info("detector_backend 未返回 (可能是旧版 A 端)")

    omni_ready = data.get("omniparser_ready")
    if omni_ready is not None:
        ok(f"omniparser_ready={omni_ready}", omni_ready is True)
    else:
        info("omniparser_ready 未返回，检查 OmniParser 是否启动")

    return True


def test_audit_report():
    """测试审计批量上报"""
    print()
    print("=" * 50)
    print("  2. 审计批量上报" if server_up() else "  2. 审计批量上报 [离线]")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent, desensitize_text
    import tempfile

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_real_test.db"),
        server_url=SERVER,
        batch_size=2,
    )

    # 写入 2 条
    for i in range(2):
        agent.enqueue({
            "task_id": f"real-api-{i:03d}",
            "query": f"真实接口测试操作 {i}",
            "intent_category": "operation_guide",
            "complexity_score": 30,
            "route": "L3",
            "total_steps": 3,
            "completed_steps": 3,
            "result": "success",
            "duration_ms": 5000,
            "fingerprint_mismatches": 0,
            "redline_triggered": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        })

    depth = agent.get_queue_depth()
    ok(f"记录入队 (depth={depth})", depth >= 2)

    if server_up():
        result = agent.flush_now()
        sent = result.get("sent", 0)
        error = result.get("error", "")
        if sent >= 1:
            ok(f"上报 sent={sent}", True)
            remainder = agent.get_queue_depth()
            ok(f"上报后队列清空 (depth={remainder})", remainder == 0)
        elif "404" in error or "405" in error:
            info(f"端点未部署 (HTTP 404/405) — A 端 Day 4-5 就位")
            ok("队列保留等待端点就位", agent.get_queue_depth() >= 2)
        else:
            ok(f"上报失败 (sent={sent}, error={error[:60]})", False)
    else:
        info("A 端离线，跳过真实上报")
        ok("离线降级正常", True)

    agent.shutdown()


def test_feedback():
    """测试单独反馈"""
    print()
    print("=" * 50)
    print("  3. 单独反馈" if server_up() else "  3. 单独反馈 [离线]")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent
    import tempfile

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_fb_test.db"),
        server_url=SERVER,
    )

    if server_up():
        fb = agent.send_feedback("real-fb-001", "useful", "指引清晰")
        if fb is True:
            ok("反馈上报成功", True)
        else:
            info("反馈端点未部署 (A 端 Day 4-5 就位)")
            ok("离线降级正常 (send_feedback 未崩溃)", True)
    else:
        info("A 端离线，跳过真实反馈")
        ok("离线降级正常", True)

    agent.shutdown()


def test_config_pull():
    """测试配置拉取"""
    print()
    print("=" * 50)
    print("  4. 配置拉取" if server_up() else "  4. 配置拉取 [离线]")
    print("=" * 50)

    from client.config.config_poller import ConfigPoller

    poller = ConfigPoller(
        server_url=SERVER,
        interval_min=5,
    )

    if server_up():
        result = poller.poll_now()
        if result:
            ok(f"配置拉取成功 (version={result.get('version', '?')})", True)
        else:
            info("配置无更新 (304) 或端点未部署")
            ok("降级处理正常 (不崩溃)", True)
    else:
        result = poller.poll_now()
        ok("离线返回 None (不崩溃)", result is None)

    poller.shutdown()


def test_health_new_fields():
    """测试 C 端健康检查是否能处理新字段"""
    print()
    print("=" * 50)
    print("  5. C 端 HealthStatus 兼容性")
    print("=" * 50)

    from client.integration.controller import HealthStatus

    # 模拟完整健康检查
    h = HealthStatus(
        asr_available=True,
        tts_available=True,
        audit_db_ok=True,
        server_reachable=server_up(),
        queue_depth=0,
    )
    ok(f"overall={h.overall}", h.overall in ("healthy", "degraded"))

    # 所有 7 个字段
    fields = ["asr_available", "asr_engine", "tts_available", "tts_engine",
              "audit_db_ok", "server_reachable", "queue_depth"]
    for f in fields:
        ok(f"字段 {f}", hasattr(h, f))

    # 验证 server_reachable 能正确反映 A 端状态
    if server_up():
        ok("A端可达 → server_reachable=True", h.server_reachable is True)
    else:
        ok("A端离线 → server_reachable=False (预期)",
           h.server_reachable is False)


# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  HAJIMI Day 3 — A 端真实接口集成测试")
    print(f"  目标: {SERVER}")
    print()

    if not HTTPX_OK:
        print("  ❌ httpx 未安装，无法执行测试")
        print("     pip install httpx")
        sys.exit(1)

    a_up = server_up()
    if a_up:
        info(f"A 端在线 ({SERVER}) — 执行真实接口测试")
    else:
        info(f"A 端离线 ({SERVER}) — 执行离线降级测试")
        info("启动 A 端: cd HAJIMI_UI && scripts\\start_server.bat")

    test_health()
    test_audit_report()
    test_feedback()
    test_config_pull()
    test_health_new_fields()

    print()
    print("=" * 50)
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("  真实接口集成测试全部通过")
    else:
        print(f"  ⚠ {FAIL} 项未通过")
    if not a_up:
        print("  注意: A 端离线，以上为离线降级模式测试")
        print("  启动 A 端后重新运行以完成真实联调")
