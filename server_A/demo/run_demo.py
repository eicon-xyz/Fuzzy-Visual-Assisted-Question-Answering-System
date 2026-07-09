"""
HAJIMI Showcase Demo - Enterprise Form Auto-Fill
=================================================
Scenario: HR assistant uses HAJIMI to auto-fill a training registration form.

One command: python demo/run_demo.py
"""
import json, sys, os, time, urllib.request, urllib.error, http.server, socketserver, threading

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
FORM_PORT = 8765
FORM_URL = f"http://127.0.0.1:{FORM_PORT}/registration_form.html"
BASE = "http://127.0.0.1:8010"
HEADERS = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}

TASK = (
    "Open browser and go to http://127.0.0.1:8765/registration_form.html, "
    "fill the registration form with Zhang San's info: "
    "name=Zhang San, phone=13812345678, email=zhangsan@startech.com, "
    "department=R&D Center, title=Senior Engineer, course=AI Automation Practice. "
    "Then submit and take a screenshot to confirm."
)

SEP = "=" * 70

# ── 1. Start local HTTP server ───────────────────────────────────────
print(SEP)
print("HAJIMI DEMO - Enterprise Form Auto-Fill")
print(SEP)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DEMO_DIR, **kwargs)
    def log_message(self, format, *args):
        pass

httpd = socketserver.TCPServer(("", FORM_PORT), QuietHandler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
print(f"\n[SETUP] Form server: {FORM_URL}")

# Verify
try:
    with urllib.request.urlopen(FORM_URL, timeout=3) as r:
        html = r.read().decode()
        assert "reg-form" in html
    print("[SETUP] Form HTML OK")
except Exception as e:
    print(f"[FATAL] Form not served: {e}")
    sys.exit(1)

# ── 2. Submit task ───────────────────────────────────────────────────
print(f"\n[TASK] {TASK}")
print("[SUBMIT] POST /api/demo/execute ...")

url = f"{BASE}/api/demo/execute"
data = json.dumps({"query": TASK, "image": None}).encode()
r = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
try:
    with urllib.request.urlopen(r, timeout=30) as resp:
        result = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"[FATAL] HTTP {e.code}")
    sys.exit(1)

if not result.get("success"):
    print(f"[FATAL] {result.get('error')}")
    sys.exit(1)

plan = result["plan"]
task_id = result["task_id"]
print(f"  task_id = {task_id}")
print(f"  goal    = {plan['goal']}")
print(f"  steps   = {plan['total_steps']}")
for s in plan["steps"]:
    print(f"    [{s['step_index']}] {s['instruction']}")

# ── 3. Stream SSE events ─────────────────────────────────────────────
print(f"\n[STREAM] Execution events:")
print("-" * 70)
url = f"{BASE}/api/demo/stream/{task_id}"
r = urllib.request.Request(url, headers={"X-Demo-Key": "hajimi-demo-2026"})

final_event = None
step_count = 0
done_count = 0

try:
    with urllib.request.urlopen(r, timeout=240) as resp:
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
                            step_count += 1
                            print(f"  --> Step {payload['step_index']}: {payload['instruction'][:100]}")

                        elif event == "step_done":
                            done_count += 1
                            summary = payload.get("action_summary", "")
                            print(f"  OK   Step {payload['step_index']} [{summary[:80]}]")

                        elif event == "step_failed":
                            print(f"  FAIL Step {payload['step_index']}: {payload.get('reason', '')[:80]}")

                        elif event == "log":
                            if payload.get("level") == "warn":
                                print(f"  WARN {payload.get('message', '')[:100]}")

                        elif event in ("task_done", "task_failed", "task_cancelled"):
                            final_event = event
except Exception as e:
    print(f"  Stream error: {e}")

# ── 4. Agent log analysis ────────────────────────────────────────────
print(f"\n[LOG] Detailed actions from agent log:")
print("-" * 70)
log_path = f"logs/agent_{task_id}.log"

tools_used = set()
field_count = 0
click_count = 0
has_submit = False
has_screenshot = False

if os.path.exists(log_path):
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # Count tool usages
        for t in ["browser_navigate", "browser_snapshot", "browser_type",
                   "browser_click", "browser_screenshot", "browser_press_key",
                   "launch_app", "mark_step_done", "get_screen_info"]:
            if f"{t}(" in s:
                tools_used.add(t)
                break

        if "browser_type(" in s:
            field_count += 1
        if "browser_click" in s and "submit" in s.lower():
            has_submit = True
        if "browser_screenshot" in s:
            has_screenshot = True

        # Print action timeline
        if any(k in s for k in ["navigate(", "browser_type(", "browser_click(",
                                 "browser_screenshot", "launch_app(",
                                 "STEP "]):
            print(f"  {s[:170]}")

    print(f"\n  Tools used: {len(tools_used)} unique - {sorted(tools_used)}")
else:
    print(f"  WARNING: log not found at {log_path}")

# ── 5. Summary ───────────────────────────────────────────────────────
print(f"\n[RESULT]")
print(SEP)

print(f"  Final event:   {final_event or 'unknown'}")
print(f"  Steps planned: {plan['total_steps']}")
print(f"  Steps done:    {done_count}/{step_count}")
print(f"  Fields filled: {field_count}")
print(f"  Submitted:     {'Yes' if has_submit else 'No'}")
print(f"  Screenshot:    {'Yes' if has_screenshot else 'No'}")
print(f"  Tools used:    {len(tools_used)} ({', '.join(sorted(tools_used))})")

# Grade
score = 0
if final_event == "task_done":
    score += 40
if field_count >= 5:
    score += 25
elif field_count >= 3:
    score += 15
if has_submit:
    score += 20
if has_screenshot:
    score += 10
if len(tools_used) >= 5:
    score += 5
print(f"  Score:         {score}/100")

print("-" * 70)
print("Demo Narrative:")
print("  Xiao Zhang is an admin assistant at StarTech Corp.")
print("  Every day she fills dozens of training registration forms manually.")
print("  With HAJIMI, she just types one sentence and the form fills itself.")
print("  3 minutes per form -> 10 seconds. That's an 18x productivity boost.")
print(SEP)

httpd.shutdown()
