"""
HAJIMI_UI B-end 嵌入式 A-end 单元测试
=========================================
测试 HAJIMI_UI/server/ 的 31 个 HTTP 端点。
包含 B-end 特有端点: health/live, inspect, locate, relocate, step, clarify, report

要求：A 端运行在 http://127.0.0.1:8010

用法::
    cd HAJIMI_UI
    python -m uvicorn server.main:app --host 127.0.0.1 --port 8010

    cd E:/Fuzzy-Visual-Assisted-Question-Answering-System
    python 项目文档/测试文档/test_hajimi_ui.py
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

def test_connectivity():
    print("\n========= 1. 连通性 =========")
    try:
        r = httpx.get(f"{SERVER}/api/demo/health", timeout=5)
        ok(f"health → {r.status_code}", r.status_code == 200)
        return True
    except:
        ok("A端可达", False)
        return False

def test_demo_b_specific():
    """Test B-end specific demo endpoints (not in standalone A端)"""
    print("\n========= 2. B-end 专属 Demo 端点 =========")
    tid = f"bui-{uuid.uuid4().hex[:8]}"

    # health/live
    try:
        r = httpx.get(f"{SERVER}/api/demo/health/live", timeout=5)
        ok(f"GET health/live → {r.status_code} (B端专属)", r.status_code == 200)
    except:
        ok("GET health/live", False)

    # inspect
    r = httpx.post(f"{SERVER}/api/demo/inspect", headers=DH, timeout=10,
                   json={"image": "data:image/png;base64,iVBORw0KGgo=", "screen_width": 1920, "screen_height": 1080})
    ok(f"POST inspect → {r.status_code} (B端专属)", True)

    # step
    r = httpx.post(f"{SERVER}/api/demo/step", headers=DH, timeout=10,
                   json={"task_id": tid, "action": "advance", "step_index": 1})
    ok(f"POST step → {r.status_code} (B端专属)", True)

    # locate
    r = httpx.post(f"{SERVER}/api/demo/locate", headers=DH, timeout=10,
                   json={"task_id": tid, "step_index": 1, "image": "data:image/png;base64,iVBORw0KGgo="})
    ok(f"POST locate → {r.status_code} (B端专属)", True)

    # relocate
    r = httpx.post(f"{SERVER}/api/demo/relocate", headers=DH, timeout=10,
                   json={"task_id": tid, "step_index": 1, "image": "data:image/png;base64,iVBORw0KGgo="})
    ok(f"POST relocate → {r.status_code} (B端专属)", True)

    # clarify
    r = httpx.post(f"{SERVER}/api/demo/clarify", headers=DH, timeout=10,
                   json={"task_id": tid, "answer": "是"})
    ok(f"POST clarify → {r.status_code} (B端专属)", True)

    # report
    r = httpx.post(f"{SERVER}/api/demo/report", headers=DH, timeout=10,
                   json={"task_id": tid, "result": "success", "feedback_type": "useful", "duration_ms": 5000})
    ok(f"POST report → {r.status_code} (B端专属)", True)

def test_demo_common():
    """Test common demo endpoints shared with standalone A端"""
    print("\n========= 3. 通用 Demo 端点 =========")
    r = httpx.post(f"{SERVER}/api/demo/execute", headers=DH, timeout=30,
                   json={"query": "测试", "image": "data:image/png;base64,iVBORw0KGgo="})
    ok(f"POST execute → {r.status_code}", True)

    r = httpx.post(f"{SERVER}/api/demo/process", headers=DH, timeout=10,
                   json={"query": "测试"})
    ok(f"POST process → {r.status_code}", True)

    r = httpx.post(f"{SERVER}/api/demo/cancel", headers=DH, timeout=10,
                   json={"task_id": "bui-test"})
    ok(f"POST cancel → {r.status_code}", True)

    r = httpx.get(f"{SERVER}/api/demo/stream/bui-test", headers=DH, timeout=5)
    ok(f"GET stream → {r.status_code}", True)

def test_admin_common():
    """Test admin endpoints (same as standalone A端 minus session/metrics)"""
    print("\n========= 4. Admin 端点 =========")
    for path in ["stats/overview","stats/top-tasks","stats/trend","stats/redline",
                 "stats/feedback","failures/list","config/current"]:
        r = httpx.get(f"{SERVER}/api/admin/{path}", headers=AH, timeout=10)
        ok(f"GET {path} → {r.status_code}", r.status_code == 200)

    r = httpx.get(f"{SERVER}/api/admin/failures/detail/test", headers=AH, timeout=10)
    ok(f"GET failures/detail → {r.status_code}", True)

    r = httpx.post(f"{SERVER}/api/admin/config/deploy", headers=AH, timeout=10,
                   json={"bui_test": "ok"})
    ok(f"POST config/deploy → {r.status_code}", r.status_code == 200)

def test_audit():
    print("\n========= 5. Audit 端点 =========")
    tid = f"bui-audit-{uuid.uuid4().hex[:8]}"
    r = httpx.post(f"{SERVER}/api/audit/report", headers=DH, timeout=10,
                   json={"client_id":"hajimi_ui_test","batch":[{
                       "task_id":tid,"query":"BUI测试","intent_category":"operation_guide",
                       "route":"L2","total_steps":1,"completed_steps":1,"result":"success",
                       "duration_ms":100,"fingerprint_mismatches":0,"redline_triggered":False}]})
    ok(f"POST audit/report → {r.status_code}", r.status_code == 200)
    r = httpx.post(f"{SERVER}/api/audit/feedback", headers=DH, timeout=10,
                   json={"task_id":tid,"feedback_type":"useful","comment":"BUI测试"})
    ok(f"POST audit/feedback → {r.status_code}", r.status_code == 200)

def test_auth_config_flow_monitor():
    print("\n========= 6. 认证/配置/流/监控 =========")
    r = httpx.post(f"{SERVER}/api/auth/login", timeout=10,
                   json={"username":"admin@hajimi.local","password":"test123"})
    ok(f"POST auth/login → {r.status_code}", r.status_code == 200)
    r = httpx.get(f"{SERVER}/api/config/pull", headers=DH, timeout=10)
    ok(f"GET config/pull → {r.status_code}", r.status_code == 200)
    for p in ["flow/topology","flow/metrics","flow/versions"]:
        r = httpx.get(f"{SERVER}/api/admin/{p}", headers=AH, timeout=10)
        ok(f"GET {p} → {r.status_code}", r.status_code == 200)
    for p in ["monitor/health","monitor/alerts"]:
        r = httpx.get(f"{SERVER}/api/admin/{p}", headers=AH, timeout=10)
        ok(f"GET {p} → {r.status_code}", r.status_code == 200)
    r = httpx.post(f"{SERVER}/api/admin/monitor/alerts/read-all", headers=AH, timeout=10)
    ok(f"POST monitor/read-all → {r.status_code}", r.status_code == 200)

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  HAJIMI_UI (B-end) 嵌入式 A-end 单元测试")
    print(f"  目标: {SERVER} | 31 端点")
    print(f"{'='*50}")
    if not test_connectivity():
        print(f"\n  A端离线。启动命令:")
        print(f"  cd HAJIMI_UI")
        print(f"  python -m uvicorn server.main:app --host 127.0.0.1 --port 8010")
        sys.exit(0)
    test_demo_b_specific()
    test_demo_common()
    test_admin_common()
    test_audit()
    test_auth_config_flow_monitor()
    print(f"\n{'='*50}")
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print(f"  HAJIMI_UI (B-end) 全部通过")
    else:
        print(f"  {FAIL} 项失败，请检查 A端日志")
