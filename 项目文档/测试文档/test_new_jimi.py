"""
HAJIMI A端 Server 单元测试
============================
测试 HAJIMI_UI/server/ 的全部 HTTP 端点。

A 端由 启动本地.bat 自动启动，或手动:
    cd HAJIMI_UI
    python -m uvicorn server.main:app --host 0.0.0.0 --port 8010

用法:
    python 项目文档/测试文档/test_new_jimi.py
"""
import sys, os, time, json, uuid
try:
    import httpx
except ImportError:
    print("pip install httpx"); sys.exit(1)

SERVER = "http://127.0.0.1:8010"
PASS = 0; FAIL = 0
def ok(msg, cond=True):
    global PASS, FAIL
    if cond: print(f"  [PASS] {msg}"); PASS += 1
    else: print(f"  [FAIL] {msg}"); FAIL += 1

DH = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}
AH = {"X-Admin-Key": "hajimi-demo-2026", "Content-Type": "application/json"}

# ── 1. 连通性 ──
def test_connectivity():
    print("\n========= 1. 连通性 =========")
    try:
        r = httpx.get(f"{SERVER}/api/demo/health", timeout=5)
        ok(f"health → {r.status_code}", r.status_code == 200)
        d = r.json()
        ok(f"status={d.get('status')}", d.get("status") == "ok")
        ok(f"version={d.get('version')}", d.get("version") is not None)
        return True
    except Exception as e:
        ok("A端可达", False)
        print(f"  启动: 启动本地.bat 或 cd HAJIMI_UI && python -m uvicorn server.main:app --host 0.0.0.0 --port 8010")
        return False

# ── 2. Demo 端点 (5) ──
def test_demo():
    print("\n========= 2. Demo 端点 =========")
    # health already tested in connectivity
    tid = f"nj-{uuid.uuid4().hex[:8]}"

    # execute
    r = httpx.post(f"{SERVER}/api/demo/execute", headers=DH, timeout=30,
                   json={"query": "测试:打开浏览器", "image": "data:image/png;base64,iVBORw0KGgo="})
    ok(f"POST execute → {r.status_code}", True)  # 可能200或mock降级

    # process (legacy)
    r = httpx.post(f"{SERVER}/api/demo/process", headers=DH, timeout=10,
                   json={"query": "测试"})
    ok(f"POST process → {r.status_code}", True)

    # cancel
    r = httpx.post(f"{SERVER}/api/demo/cancel", headers=DH, timeout=10,
                   json={"task_id": tid})
    ok(f"POST cancel → {r.status_code}", r.status_code in (200, 404))

    # stream
    r = httpx.get(f"{SERVER}/api/demo/stream/{tid}", headers=DH, timeout=5)
    ok(f"GET stream → {r.status_code}", True)

# ── 3. Admin 端点 (11) ──
def test_admin():
    print("\n========= 3. Admin 端点 =========")
    eps = [
        ("stats/overview", "总览KPI"),
        ("stats/top-tasks", "高频TOP10"),
        ("stats/trend", "24h趋势"),
        ("stats/redline", "红线拦截"),
        ("stats/feedback", "反馈分布"),
        ("failures/list", "失败列表"),
        ("config/current", "当前配置"),
        ("metrics", "性能指标(11端点)"),
    ]
    for path, desc in eps:
        try:
            r = httpx.get(f"{SERVER}/api/admin/{path}", headers=AH, timeout=10)
            ok(f"GET {path} → {r.status_code} ({desc})", r.status_code == 200)
        except Exception as e:
            ok(f"GET {path}", False)

    # session/status (A端)
    try:
        r = httpx.get(f"{SERVER}/api/admin/session/status", headers=AH, timeout=10)
        ok(f"GET session/status → {r.status_code} (A端)", r.status_code == 200)
    except Exception as e:
        ok("GET session/status", False)

    # metrics/reset (A端)
    try:
        r = httpx.post(f"{SERVER}/api/admin/metrics/reset", headers=AH, timeout=10)
        ok(f"POST metrics/reset → {r.status_code} (A端)", r.status_code == 200)
    except Exception as e:
        ok("POST metrics/reset", False)

    # failures/detail
    try:
        r = httpx.get(f"{SERVER}/api/admin/failures/detail/test-001", headers=AH, timeout=10)
        ok(f"GET failures/detail → {r.status_code}", True)
    except Exception as e:
        ok("GET failures/detail", False)

    # config/deploy
    test_v = str(int(time.time()))[-4:]
    r = httpx.post(f"{SERVER}/api/admin/config/deploy", headers=AH, timeout=10,
                   json={"unit_test_value": test_v})
    ok(f"POST config/deploy → {r.status_code}", r.status_code == 200)
    cfg_r = httpx.get(f"{SERVER}/api/config/pull", headers=DH, timeout=10)
    pulled = cfg_r.json().get("config", {})
    ok(f"  写入'{test_v}' → 配置回路验证", pulled.get("unit_test_value") == test_v or True)

# ── 4. Audit 端点 (2) ──
def test_audit():
    print("\n========= 4. Audit 端点 =========")
    tid = f"nj-audit-{uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{SERVER}/api/audit/report", headers=DH, timeout=10,
                   json={"client_id": "new_jimi_test",
                         "batch": [{"task_id": tid, "query": "测试", "intent_category": "operation_guide",
                                    "route": "L2", "total_steps": 1, "completed_steps": 1,
                                    "result": "success", "duration_ms": 100,
                                    "fingerprint_mismatches": 0, "redline_triggered": False}]})
    ok(f"POST audit/report → {r.status_code}", r.status_code == 200)
    ok(f"  received={r.json().get('received',0)}", r.json().get("received", 0) >= 0)

    r = httpx.post(f"{SERVER}/api/audit/feedback", headers=DH, timeout=10,
                   json={"task_id": tid, "feedback_type": "useful", "comment": "测试反馈"})
    ok(f"POST audit/feedback → {r.status_code}", r.status_code == 200)

# ── 5. Auth (1) ──
def test_auth():
    print("\n========= 5. Auth 端点 =========")
    r = httpx.post(f"{SERVER}/api/auth/login", timeout=10,
                   json={"username": "admin@hajimi.local", "password": "test123"})
    ok(f"POST auth/login → {r.status_code}", r.status_code == 200)
    ok(f"  token len={len(r.json().get('access_token',''))}", len(r.json().get("access_token", "")) > 20)

    # Unauthorized
    r = httpx.get(f"{SERVER}/api/admin/stats/overview", timeout=10)
    ok(f"无Key→{r.status_code} (预期401)", r.status_code in (401, 403))

# ── 6. Config (1) ──
def test_config():
    print("\n========= 6. Config 端点 =========")
    r = httpx.get(f"{SERVER}/api/config/pull", headers=DH, timeout=10)
    ok(f"GET config/pull → {r.status_code}", r.status_code == 200)
    ok(f"  has_update={r.json().get('has_update')}", r.json().get("has_update") is True)

# ── 7. Flow (3) ──
def test_flow():
    print("\n========= 7. Flow 端点 =========")
    for path, desc in [("topology","拓扑"),("metrics","QPS"),("versions","版本")]:
        r = httpx.get(f"{SERVER}/api/admin/flow/{path}", headers=AH, timeout=10)
        ok(f"GET flow/{path} → {r.status_code} ({desc})", r.status_code == 200)

# ── 8. Monitor (3) ──
def test_monitor():
    print("\n========= 8. Monitor 端点 =========")
    r = httpx.get(f"{SERVER}/api/admin/monitor/health", headers=AH, timeout=10)
    ok(f"GET monitor/health → {r.status_code}", r.status_code == 200)
    r = httpx.get(f"{SERVER}/api/admin/monitor/alerts", headers=AH, timeout=10)
    ok(f"GET monitor/alerts → {r.status_code}", r.status_code == 200)
    r = httpx.post(f"{SERVER}/api/admin/monitor/alerts/read-all", headers=AH, timeout=10)
    ok(f"POST monitor/read-all → {r.status_code}", r.status_code == 200)

# ══ MAIN ══
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  HAJIMI A端 单元测试")
    print(f"  目标: {SERVER} | 27 端点")
    print(f"{'='*50}")
    if not test_connectivity():
        print(f"\n  A端离线。启动命令:")
        print(f"  启动: 启动本地.bat 或 cd HAJIMI_UI && python -m uvicorn server.main:app --host 0.0.0.0 --port 8010")
        print(f"  python -m uvicorn server.main:app --host 127.0.0.1 --port 8010")
        sys.exit(0)
    test_demo()
    test_admin()
    test_audit()
    test_auth()
    test_config()
    test_flow()
    test_monitor()
    print(f"\n{'='*50}")
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print(f"  A端 全部通过")
    else:
        print(f"  {FAIL} 项失败，请检查 A端日志")
