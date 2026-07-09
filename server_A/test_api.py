"""
HAJIMI local integration test — mimics Postman call chain
Usage: python test_api.py
"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8010"
HEADERS = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}


def req(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health():
    code, data = req("GET", "/api/demo/health")
    print(f"[HEALTH] {code} - omniparser_ready={data.get('omniparser_ready')}")
    # Accept 200 or 503 (degraded without OmniParser is fine)
    return code in (200, 503)


def test_execute(query="open calculator"):
    code, data = req("POST", "/api/demo/execute", {"query": query, "image": None})
    if code == 200:
        print(f"[EXECUTE] {code} - task_id={data['task_id']}, goal={data['plan']['goal']}")
        return data["task_id"]
    else:
        print(f"[EXECUTE] {code} - {data.get('error', {}).get('message', data)}")
        return None


def test_stream(task_id, timeout=20):
    """SSE stream - read events until task_done/task_failed or timeout."""
    print(f"[STREAM] listening on task_id={task_id} ...")
    url = f"{BASE}/api/demo/stream/{task_id}"
    r = urllib.request.Request(url, headers={"X-Demo-Key": "hajimi-demo-2026"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            buffer = b""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk
                while b"\n\n" in buffer:
                    line, buffer = buffer.split(b"\n\n", 1)
                    text = line.decode("utf-8", errors="replace")
                    for part in text.split("\n"):
                        if part.startswith("event: "):
                            event = part[7:]
                        elif part.startswith("data: "):
                            payload = json.loads(part[6:])
                            print(f"  -> {event}: {json.dumps(payload, ensure_ascii=False)[:120]}")
                            if event in ("task_done", "task_failed", "task_cancelled"):
                                return event
    except Exception as e:
        print(f"[STREAM] timeout or error: {e}")
        return None


def test_admin_stats():
    headers = {"X-Admin-Key": "hajimi-demo-2026"}
    url = f"{BASE}/api/admin/stats/overview"
    r = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(r, timeout=10) as resp:
        data = json.loads(resp.read())
        print(f"[ADMIN] total_transactions={data.get('total_transactions')}, "
              f"l2={data.get('l2_count')}, l3={data.get('l3_count')}")


def check_memories():
    """Check if memories were persisted."""
    try:
        from server.database import init_db, SessionLocal
        from server.database.models import Memory
        init_db()
        db = SessionLocal()
        rows = db.query(Memory).filter(Memory.is_active == True).order_by(
            Memory.created_at.desc()).limit(5).all()
        db.close()
        print(f"[MEMORY] active memories: {len(rows)}")
        for m in rows:
            print(f"  [{m.memory_type}] {m.summary[:80]}")
    except Exception as e:
        print(f"[MEMORY] check failed: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("HAJIMI Integration Test")
    print("=" * 60)

    # 1. Health
    if not test_health():
        print("FAIL: service not ready, start with: python server/main.py")
        exit(1)

    # 2. Execute
    task_id = test_execute("open calculator")
    if not task_id:
        print("FAIL: planning failed")
        exit(1)

    # 3. Stream
    result = test_stream(task_id, timeout=25)
    if result == "task_done":
        print("OK: task completed successfully")
    elif result == "task_failed":
        print("INFO: task failed (expected without real screenshot)")
    else:
        print("INFO: no terminal event received (timeout)")

    # 4. Admin
    test_admin_stats()

    # 5. Memory
    check_memories()

    print("=" * 60)
    print("Done.")
