"""
HAJIMI GitHub Trending Demo — Markdown Report
===============================================
Scenario: Browser navigates to GitHub Trending, extracts top 3 Python repos,
          writes a markdown report file to Desktop.

Capabilities demonstrated:
  - Browser: navigate, scroll, snapshot (DOM reading)
  - Desktop: launch_app, type_text (content generation), press_key (Ctrl+S save)
  - Cross-app: web → desktop file output
"""
import json, sys, os, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8010"
HEADERS = {"X-Demo-Key": "hajimi-demo-2026", "Content-Type": "application/json"}

# Task: structured for proper step decomposition
# The planning agent now has a few-shot example teaching it to split
# browser + desktop into separate steps
TASK = (
    "Open browser, go to https://github.com/trending/python?since=daily, "
    "scroll down 400px and read the repo list from the snapshot. "
    "Then open Notepad and write the results as a markdown file: "
    "title '# GitHub Python Trending Top 3', each repo as a subsection "
    "with name and stars. Save to Desktop as 'github_trending.md'."
)

SEP = "=" * 70
print(SEP)
print("HAJIMI — GitHub Trending Markdown Reporter")
print("Browser → Extract → Save as .md to Desktop")
print(SEP)

# ── 1. Submit ──────────────────────────────────────────────────────────
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

# ── 2. Stream ──────────────────────────────────────────────────────────
print(f"\n[STREAM] Execution events:")
print("-" * 70)
url = f"{BASE}/api/demo/stream/{task_id}"
r = urllib.request.Request(url, headers={"X-Demo-Key": "hajimi-demo-2026"})

final_event = None
step_results = {}

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
                            instr = payload["instruction"][:120]
                            print(f"  >> Step {si}: {instr}")
                            step_results[si] = {"instruction": instr, "status": "executing"}

                        elif event == "step_done":
                            si = payload["step_index"]
                            summary = payload.get("action_summary", "")
                            print(f"  OK  Step {si}: {summary[:120]}")
                            step_results.setdefault(si, {})["status"] = "done"

                        elif event == "step_failed":
                            si = payload["step_index"]
                            reason = payload.get("reason", "")
                            print(f"  XX  Step {si} FAILED: {reason[:120]}")
                            step_results.setdefault(si, {})["status"] = "failed"

                        elif event == "log":
                            if payload.get("level") == "warn":
                                print(f"  WARN: {payload.get('message', '')[:150]}")

                        elif event in ("task_done", "task_failed", "task_cancelled"):
                            print(f"\n  ==== {event} ====")
                            print(f"  {json.dumps(payload, ensure_ascii=False)[:300]}")
                            final_event = event
except Exception as e:
    print(f"  Stream error: {e}")

# ── 3. Agent log analysis ──────────────────────────────────────────────
print(f"\n[TRACE] Agent log: logs/agent_{task_id}.log")
print("-" * 70)
log_path = f"logs/agent_{task_id}.log"

browser_tools = set()
desktop_tools = set()
repos_extracted = False
ctrl_s_used = False

if os.path.exists(log_path):
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        s = line.strip()
        if not s:
            continue

        for t in ["browser_navigate", "browser_snapshot", "browser_scroll",
                   "browser_click", "browser_screenshot"]:
            if f"{t}(" in s:
                browser_tools.add(t)
                break
        for t in ["launch_app", "type_text", "press_key", "get_screen_info"]:
            if f"{t}(" in s:
                desktop_tools.add(t)
                break

        if any(kw in s.lower() for kw in ["kyutai", "hesreallyhim", "langbot",
                                            "mvanhorn", "awesome-claude",
                                            "pocket-tts", "last30days", "ghost",
                                            "bradautomates"]):
            repos_extracted = True
        if "ctrl+s" in s.lower():
            ctrl_s_used = True

        # Print key action lines
        if any(k in s for k in ["STEP ", "browser_navigate", "browser_scroll",
                                 "browser_snapshot", "launch_app", "type_text",
                                 "press_key", "mark_step_done"]):
            print(f"  {s[:180]}")

    all_tools = browser_tools | desktop_tools | {"mark_step_done"}
    print(f"\n  Browser tools: {sorted(browser_tools)}")
    print(f"  Desktop tools: {sorted(desktop_tools)}")
    print(f"  Unique:        {len(all_tools)}")
else:
    print(f"  WARNING: log not found at {log_path}")

# ── 4. Check output file ───────────────────────────────────────────────
print(f"\n[OUTPUT]")
print("-" * 70)
desktop = os.path.expanduser("~/Desktop")
report_path = os.path.join(desktop, "github_trending.md")
if os.path.exists(report_path):
    print(f"  '{report_path}' exists!")
    with open(report_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    print(f"  Size: {len(content)} chars")
    print(f"  Content preview:")
    for line in content.split("\n")[:15]:
        print(f"    {line[:120]}")
else:
    print(f"  NOTE: '{report_path}' not found (agent may have pasted content to Notepad but not saved)")

# ── 5. Summary ─────────────────────────────────────────────────────────
print(f"\n[RESULT]")
print(SEP)

done = sum(1 for r in step_results.values() if r.get("status") == "done")
total = len(step_results)

print(f"  Final:         {final_event or 'unknown'}")
print(f"  Steps:         {done}/{total} completed")
print(f"  Browser tools: {len(browser_tools)} ({', '.join(sorted(browser_tools))})")
print(f"  Desktop tools: {len(desktop_tools)} ({', '.join(sorted(desktop_tools))})")
print(f"  Repos found:   {'Yes' if repos_extracted else 'No'}")
print(f"  Ctrl+S used:   {'Yes' if ctrl_s_used else 'No'}")

score = 0
if final_event == "task_done":
    score += 30
if repos_extracted:
    score += 25
if ctrl_s_used:
    score += 20
if len(browser_tools) >= 3:
    score += 15
if len(desktop_tools) >= 2:
    score += 10
print(f"  Score:         {score}/100")

print("-" * 70)
print("Why this matters (vs any AI chatbot):")
print("  [Browser]  Real Chrome opens, scrolls, reads DOM — not API calls")
print("  [Desktop]  Opens Notepad, writes content, saves to disk")
print("  [Bridge]   Web data → local .md file — no copy-paste needed")
print(SEP)
