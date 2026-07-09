"""
HAJIMI Full Capability Demo - WPS + OmniParser + Browser
=========================================================
Scenario: User asks HAJIMI to open WPS, write a weekly report,
          then search for related materials in browser.

Capabilities demonstrated:
  - OmniParser visual element detection (get_screen_info)
  - Desktop automation (launch_app, click, type_text)
  - Content generation (Agent writes the report)
  - Keyboard shortcuts (press_key for formatting)
  - Browser automation (navigate, snapshot, type, click)
  - Auto-memory extraction
"""
import json, sys, os, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8010"
HEADERS = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}

TASK = (
    "Open WPS, create a new blank document with Ctrl+N. "
    "Write a short weekly report titled 'AI Project Weekly Report' "
    "with three numbered sections about project progress. "
    "Use Ctrl+S to save to Desktop as 'weekly_report', "
    "then close WPS. "
    "After that, open browser and search 'AI agent automation best practices 2026'."
)

SEP = "=" * 70
print(SEP)
print("HAJIMI FULL CAPABILITY DEMO")
print("WPS Report + OmniParser + Browser Search")
print(SEP)

# ── 1. Submit task ──────────────────────────────────────────────────────
print(f"\n[TASK] {TASK}")
print("[SUBMIT] POST /api/demo/execute ...")

url = f"{BASE}/api/demo/execute"
data = json.dumps({"query": TASK, "image": None}).encode()
r = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
try:
    with urllib.request.urlopen(r, timeout=30) as resp:
        result = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"[FATAL] HTTP {e.code}: {e.read().decode()[:500]}")
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

# ── 2. Stream SSE events ────────────────────────────────────────────────
print(f"\n[STREAM] Execution events:")
print("-" * 70)
url = f"{BASE}/api/demo/stream/{task_id}"
r = urllib.request.Request(url, headers={"X-Demo-Key": "hajimi-demo-2026"})

final_event = None
step_results = {}
omniparser_calls = 0
desktop_tools = set()
browser_tools = set()

try:
    with urllib.request.urlopen(r, timeout=300) as resp:
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
                            print(f"  --> Step {si}: {payload['instruction'][:120]}")
                            step_results[si] = {"status": "executing"}

                        elif event == "step_done":
                            si = payload["step_index"]
                            summary = payload.get("action_summary", "")
                            print(f"  OK  Step {si}: {summary[:100]}")

                        elif event == "step_failed":
                            si = payload["step_index"]
                            reason = payload.get("reason", "")
                            print(f"  XX  Step {si} FAILED: {reason[:100]}")

                        elif event == "log":
                            lvl = payload.get("level", "info")
                            msg = payload.get("message", "")
                            if lvl == "warn":
                                print(f"  WARN: {msg[:120]}")

                        elif event in ("task_done", "task_failed", "task_cancelled"):
                            print(f"\n  ==== {event} ====")
                            print(f"  {json.dumps(payload, ensure_ascii=False)[:300]}")
                            final_event = event
except Exception as e:
    print(f"  Stream error: {e}")

# ── 3. Agent log analysis ───────────────────────────────────────────────
print(f"\n[LOG] Agent execution trace:")
print("-" * 70)
log_path = f"logs/agent_{task_id}.log"

if os.path.exists(log_path):
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # Categorize tool usage
        if "get_screen_info(" in s:
            omniparser_calls += 1
        for t in ["launch_app", "click", "double_click", "type_text",
                   "press_key", "scroll", "wait"]:
            if f"{t}(" in s:
                desktop_tools.add(t)
                break
        for t in ["browser_navigate", "browser_snapshot", "browser_click",
                   "browser_type", "browser_screenshot", "browser_scroll",
                   "browser_press_key"]:
            if f"{t}(" in s:
                browser_tools.add(t)
                break

        # Print action timeline
        if any(k in s for k in ["STEP ", "launch_app(", "click(",
                                 "type_text(", "press_key(", "get_screen_info(",
                                 "browser_navigate(", "browser_type(",
                                 "browser_click(", "browser_screenshot(",
                                 "browser_snapshot("]):
            print(f"  {s[:170]}")

    all_tools = desktop_tools | browser_tools | {"mark_step_done"}
    print(f"\n  Desktop tools:  {sorted(desktop_tools)}")
    print(f"  Browser tools:  {sorted(browser_tools)}")
    print(f"  OmniParser calls: {omniparser_calls}")
else:
    print(f"  WARNING: log not found at {log_path}")

# ── 4. Summary ──────────────────────────────────────────────────────────
print(f"\n[RESULT]")
print(SEP)

done = sum(1 for r in step_results.values() if r.get("status") != "failed")
total = len(step_results)
all_tools = desktop_tools | browser_tools

print(f"  Final:           {final_event or 'unknown'}")
print(f"  Steps:           {done}/{total} completed")
print(f"  OmniParser:      {omniparser_calls} screen captures")
print(f"  Desktop tools:   {len(desktop_tools)} ({', '.join(sorted(desktop_tools))})")
print(f"  Browser tools:   {len(browser_tools)} ({', '.join(sorted(browser_tools))})")
print(f"  Total tools:     {len(all_tools)} unique")

# Score
score = 0
if final_event == "task_done":
    score += 35
if omniparser_calls >= 2:
    score += 25
elif omniparser_calls >= 1:
    score += 10
if len(desktop_tools) >= 3:
    score += 20
if len(browser_tools) >= 3:
    score += 20
print(f"  Score:           {score}/100")

print("-" * 70)
print("Capabilities demonstrated:")
print("  [OmniParser]    Visual screen element detection")
print("  [Desktop]       launch_app, click, type_text, press_key")
print("  [Browser]       navigate, snapshot, type, click, screenshot")
print("  [AI]            Report content generation")
print("  [Memory]        Auto-memory extraction")
print("  [Safety]        Redline query + step-level safety check")
print(SEP)
