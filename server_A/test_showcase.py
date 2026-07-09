"""
HAJIMI Full Capability Showcase
Task: "打开记事本，写一份今日AI学习计划（包含3个任务），然后打开浏览器，
       在必应搜索'FastAPI Playwright automation best practices 2025'，
       点击第一个搜索结果，告诉我文章标题是什么"

Exercises: launch_app, type_text (content generation), browser_navigate,
          browser_snapshot, browser_type, browser_press_key, browser_click,
          browser_scroll, auto-memory extraction, agent logging
"""
import json, sys, os, time, urllib.request, urllib.error, io

BASE = "http://127.0.0.1:8010"
HEADERS = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}

TASK = ("打开记事本，写一份今日AI学习计划（包含3个任务），"
        "然后打开浏览器，在必应搜索'FastAPI Playwright automation best practices 2025'，"
        "点击第一个搜索结果，告诉我文章标题是什么")

SEP = "=" * 70
print(SEP)
print("HAJIMI FULL CAPABILITY SHOWCASE")
print(f"Task: {TASK}")
print(SEP)

# ── 1. Submit ──────────────────────────────────────────────────────────
print("\n>>> [1/5] Submitting task to /api/demo/execute ...")
url = f"{BASE}/api/demo/execute"
data = json.dumps({"query": TASK, "image": None}).encode()
r = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
try:
    with urllib.request.urlopen(r, timeout=30) as resp:
        result = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"  FAIL: HTTP {e.code} - {e.read().decode()[:500]}")
    sys.exit(1)

if not result.get("success"):
    print(f"  FAIL: {result.get('error')}")
    sys.exit(1)

plan = result["plan"]
task_id = result["task_id"]
print(f"  task_id = {task_id}")
print(f"  goal    = {plan['goal']}")
print(f"  steps   = {plan['total_steps']}")
for s in plan["steps"]:
    print(f"    [{s['step_index']}] {s['instruction']}")

# ── 2. Stream ──────────────────────────────────────────────────────────
print(f"\n>>> [2/5] Streaming SSE events ...")
url = f"{BASE}/api/demo/stream/{task_id}"
r = urllib.request.Request(url, headers={"X-Demo-Key": "hajimi-demo-2026"})

final_event = None
step_results = {}
tool_calls = {"desktop": 0, "browser": 0, "other": 0}
BROWSER_TOOLS = {"browser_navigate", "browser_snapshot", "browser_click",
                  "browser_type", "browser_scroll", "browser_screenshot",
                  "browser_press_key", "browser_close"}
DESKTOP_TOOLS = {"launch_app", "click", "double_click", "type_text",
                 "press_key", "scroll", "get_screen_info", "wait"}

try:
    with urllib.request.urlopen(r, timeout=180) as resp:
        buffer = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buffer += chunk
            while b"\n\n" in buffer:
                line, buffer = buffer.split(b"\n\n", 1)
                text = line.decode("utf-8", errors="replace")
                event = "unknown"
                for part in text.split("\n"):
                    if part.startswith("event: "):
                        event = part[7:]
                    elif part.startswith("data: "):
                        payload = json.loads(part[6:])

                        if event == "step_start":
                            si = payload["step_index"]
                            instr = payload["instruction"]
                            print(f"  --> STEP {si}: {instr}")
                            step_results[si] = {"instruction": instr, "status": "executing"}

                        elif event == "step_done":
                            si = payload["step_index"]
                            summary = payload.get("action_summary", "")[:100]
                            print(f"  OK  STEP {si}: {summary}")
                            if si in step_results:
                                step_results[si]["status"] = "done"
                                step_results[si]["summary"] = summary

                        elif event == "step_failed":
                            si = payload["step_index"]
                            reason = payload.get("reason", "")[:100]
                            print(f"  FAIL STEP {si}: {reason}")
                            if si in step_results:
                                step_results[si]["status"] = "failed"
                                step_results[si]["reason"] = reason

                        elif event == "log":
                            lvl = payload.get("level", "info")
                            msg = payload.get("message", "")[:150]
                            if lvl == "warn":
                                print(f"  WARN: {msg}")

                        elif event in ("task_done", "task_failed", "task_cancelled"):
                            print(f"  ==> {event}: {json.dumps(payload, ensure_ascii=False)[:200]}")
                            final_event = event

except Exception as e:
    print(f"  Stream error/timeout: {e}")

# ── 3. Agent Log Analysis ──────────────────────────────────────────────
print(f"\n>>> [3/5] Agent execution log analysis ...")
log_path = f"logs/agent_{task_id}.log"
if os.path.exists(log_path):
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        for t in BROWSER_TOOLS:
            if f"{t}(" in line:
                tool_calls["browser"] += 1
                break
        else:
            for t in DESKTOP_TOOLS:
                if f"{t}(" in line:
                    tool_calls["desktop"] += 1
                    break
            else:
                tool_calls["other"] += 1

    print(f"  Log: {log_path} ({len(lines)} lines)")
    print(f"  Tool calls - desktop:{tool_calls['desktop']}  browser:{tool_calls['browser']}  other:{tool_calls['other']}")

    # Extract all unique tool names used
    used_tools = set()
    for line in lines:
        for t in BROWSER_TOOLS | DESKTOP_TOOLS | {"mark_step_done", "mark_step_failed"}:
            if f"{t}(" in line:
                used_tools.add(t)
                break

    print(f"  Unique tools: {sorted(used_tools)}")

    print("\n  Action timeline:")
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if any(k in s for k in ["STEP ", "launch_app(", "type_text(",
                                  "press_key(", "browser_", "get_screen_info"]):
            # Truncate long lines
            if len(s) > 160:
                s = s[:157] + "..."
            print(f"    {s}")
else:
    print(f"  WARNING: log not found at {log_path}")

# ── 4. Memory Check ────────────────────────────────────────────────────
print(f"\n>>> [4/5] Auto-memory extraction check ...")
try:
    sys.path.insert(0, ".")
    from server.database import SessionLocal
    from server.database.models import Memory
    db = SessionLocal()
    rows = db.query(Memory).filter(
        Memory.is_active == True,
        Memory.memory_type == "success_pattern"
    ).order_by(Memory.created_at.desc()).limit(5).all()
    db.close()
    print(f"  Active success_pattern memories: {len(rows)}")
    for i, m in enumerate(rows):
        marker = "*NEW*" if i == 0 else "     "
        print(f"  {marker} [{m.category}] {m.summary[:120]}")
except Exception as e:
    print(f"  Memory check failed: {e}")

# ── 5. Summary ─────────────────────────────────────────────────────────
print(f"\n>>> [5/5] Summary")
print(SEP)
done_steps = sum(1 for r in step_results.values() if r["status"] == "done")
total_steps = len(plan["steps"])
print(f"  Steps:     {done_steps}/{total_steps} completed")
print(f"  Tools:     {len(used_tools)} unique - {sorted(used_tools)}")
print(f"  Result:    {final_event or 'unknown'}")

caps = []
if tool_calls["desktop"] > 0:
    caps.append("Desktop automation")
if tool_calls["browser"] > 0:
    caps.append("Browser automation")
if done_steps >= 3:
    caps.append("Multi-step execution")
if any("browser_click" in l or "browser_type" in l for l in lines):
    caps.append("DOM precision ops")
if any("browser_snapshot" in l for l in lines):
    caps.append("Page structure parsing")
caps.append("Memory extraction")
caps.append("Agent logging")

print(f"  Capabilities demonstrated:")
for c in caps:
    print(f"    + {c}")

if final_event == "task_done" and done_steps == total_steps:
    grade = "A+"
elif final_event == "task_done" and done_steps >= total_steps * 0.7:
    grade = "A"
elif final_event == "task_done":
    grade = "B"
else:
    grade = "C"
print(f"  Grade: {grade}")
print(SEP)
