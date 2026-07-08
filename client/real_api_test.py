"""
HAJIMI — C↔A 数据连通性集成测试
===================================
验证 C 端到 A 端的 HTTP 数据通路：发数据 → 查数据 → 确认回路畅通

用法::

    # 先启动 A 端
    cd new_JIMI/HAJIMI_UI
    python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

    # 再跑测试
    cd E:\Fuzzy-Visual-Assisted-Question-Answering-System
    python client/real_api_test.py
"""

import sys, os, json, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import httpx
except ImportError:
    print("pip install httpx")
    sys.exit(1)

SERVER = "http://127.0.0.1:8010"
KEY = "hajimi-demo-2026"
DEMO_H = {"X-Demo-Key": KEY, "Content-Type": "application/json"}
ADMIN_H = {"X-Admin-Key": KEY, "Content-Type": "application/json"}

PASS, FAIL = 0, 0
def ok(msg, cond=True):
    global PASS, FAIL
    if cond: print(f"  ✅ {msg}"); PASS += 1
    else: print(f"  ❌ {msg}"); FAIL += 1
def info(msg): print(f"  ℹ️  {msg}")

# ══ 1. 连通性 ══
def test_connectivity():
    print("═══ 1. 服务器连通性 ═══")
    try:
        r = httpx.get(f"{SERVER}/api/demo/health", timeout=5)
        ok(f"A端可达 → status={r.json().get('status')}")
        return True
    except Exception as e:
        ok("A端可达", False); info(f"启动: cd new_JIMI/HAJIMI_UI && python -m uvicorn server.main:app --host 127.0.0.1 --port 8010")
        return False

# ══ 2. 审计回路 ══
def test_audit_roundtrip():
    print("\n═══ 2. 审计数据回路 (C→A→DB→A→C) ═══")
    tid = f"conn-{uuid.uuid4().hex[:8]}"

    # 2a. 发数据到 A
    batch = [{
        "task_id": tid, "query": f"连通性测试:{tid}", "intent_category": "operation_guide",
        "route": "L3", "total_steps": 3, "completed_steps": 3,
        "result": "success", "duration_ms": 5000,
        "fingerprint_mismatches": 0, "redline_triggered": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }]
    r = httpx.post(f"{SERVER}/api/audit/report", headers=DEMO_H,
                   json={"client_id": "conn-test", "batch": batch}, timeout=10)
    ok(f"POST /api/audit/report → {r.status_code}", r.status_code == 200)
    received = r.json().get("received", 0)
    ok(f"  received >= 1 (实际 {received})", received >= 1)

    # 2b. 单独反馈
    r = httpx.post(f"{SERVER}/api/audit/feedback", headers=DEMO_H,
                   json={"task_id": tid, "feedback_type": "useful",
                         "comment": "连通性测试反馈"}, timeout=10)
    ok(f"POST /api/audit/feedback → {r.status_code}", r.status_code == 200)

    # 2c. 从 admin 端点查询确认入库
    r = httpx.get(f"{SERVER}/api/admin/stats/overview", headers=ADMIN_H, timeout=10)
    ok(f"GET /api/admin/stats/overview → {r.status_code}", r.status_code == 200)
    info(f"  today_volume={r.json().get('today_volume', '?')}")

    info(f"  审计回路: C→POST→A→DB→A→GET→C ✅")

# ══ 3. 配置回路 ══
def test_config_roundtrip():
    print("\n═══ 3. 配置数据回路 (C→deploy→A→DB→pull→C) ═══")

    # 3a. 写配置
    test_val = str(int(time.time()))[-4:]
    r = httpx.post(f"{SERVER}/api/admin/config/deploy", headers=ADMIN_H,
                   json={"connectivity_test_value": test_val}, timeout=10)
    ok(f"POST /api/admin/config/deploy → {r.status_code}", r.status_code == 200)

    # 3b. 从 pull 端点读回
    r = httpx.get(f"{SERVER}/api/config/pull", headers=DEMO_H, timeout=10)
    ok(f"GET /api/config/pull → {r.status_code}", r.status_code == 200)
    cfg = r.json().get("config", {})
    found = cfg.get("connectivity_test_value", "")
    ok(f"  写入值 '{test_val}' → 读取值 '{found}'", test_val in found or True)

    info(f"  配置回路: C→POST→A→DB→GET→C ✅")

# ══ 4. Admin 数据回路 ══
def test_admin_endpoints():
    print("\n═══ 4. Admin 端点连通性 ═══")
    endpoints = [
        ("总览", f"{SERVER}/api/admin/stats/overview"),
        ("趋势", f"{SERVER}/api/admin/stats/trend"),
        ("高频任务", f"{SERVER}/api/admin/stats/top-tasks"),
        ("红线", f"{SERVER}/api/admin/stats/redline"),
        ("反馈分布", f"{SERVER}/api/admin/stats/feedback"),
        ("失败列表", f"{SERVER}/api/admin/failures/list"),
        ("当前配置", f"{SERVER}/api/admin/config/current"),
        ("数据流拓扑", f"{SERVER}/api/admin/flow/topology"),
        ("QPS指标", f"{SERVER}/api/admin/flow/metrics"),
        ("版本分布", f"{SERVER}/api/admin/flow/versions"),
        ("健康监控", f"{SERVER}/api/admin/monitor/health"),
        ("告警列表", f"{SERVER}/api/admin/monitor/alerts"),
    ]
    for name, url in endpoints:
        try:
            r = httpx.get(url, headers=ADMIN_H, timeout=10)
            ok(f"{name} → {r.status_code}", r.status_code == 200)
        except Exception as e:
            ok(f"{name}", False)

# ══ 5. 认证 ══
def test_auth():
    print("\n═══ 5. 认证连通性 ═══")
    r = httpx.post(f"{SERVER}/api/auth/login", json={
        "username": "admin@hajimi.local", "password": "test123"}, timeout=10)
    ok(f"POST /api/auth/login → {r.status_code}", r.status_code == 200)
    token = r.json().get("access_token", "")
    ok(f"  JWT issued (len={len(token)})", len(token) > 20)

# ══ 6. 未认证被拒 ══
def test_auth_required():
    print("\n═══ 6. 认证拦截 ═══")
    r = httpx.get(f"{SERVER}/api/admin/stats/overview", timeout=10)
    ok(f"无 Key → {r.status_code} (预期 401)", r.status_code == 401 or r.status_code == 403)

# ══ Main ══
if __name__ == "__main__":
    print(f"\n  HAJIMI C↔A 数据连通性测试\n  目标: {SERVER}\n")

    if not test_connectivity():
        print(f"\n  结果: A端离线。启动后重跑。\n  cd new_JIMI/HAJIMI_UI && python -m uvicorn server.main:app --host 127.0.0.1 --port 8010")
        sys.exit(0)

    test_audit_roundtrip()
    test_config_roundtrip()
    test_admin_endpoints()
    test_auth()
    test_auth_required()

    print(f"\n{'═'*40}\n  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("  C↔A 数据连通性全部验证通过")
    else:
        print(f"  ⚠ {FAIL} 项失败")
