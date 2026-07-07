#!/usr/bin/env python
"""Quick test script for HAJIMI L5 Sidecar pipeline (:8011)."""
import os

os.environ.update(OMNIPARSER_URL="http://127.0.0.1:9800", OMNIPARSER_TIMEOUT="30")
import sys

sys.path.insert(0, ".")
import json
import time
import urllib.request

from config import DEMO_KEY, L5_API_URL
from core.screen_capture import capture_to_base64

b64 = capture_to_base64(exclude_self=True, fmt="PNG")
assert b64, "Screen capture failed!"

base = L5_API_URL.rstrip("/")
queries = [
    "打开网易云音乐，然后放一首歌",
    "打开计算器",
]

for q in queries:
    t0 = time.time()
    data = json.dumps({"query": q, "image": b64}).encode()
    req = urllib.request.Request(
        f"{base}/api/demo/execute",
        data=data,
        headers={"Content-Type": "application/json", "X-Demo-Key": DEMO_KEY},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    elapsed = time.time() - t0

    print(f"\n=== {q} ({elapsed:.1f}s) ===")
    print(f"Goal: {resp['plan']['goal']}")
    for s in resp["plan"]["steps"]:
        c = s.get("params") or "-"
        print(f"  [{s['action']:12s}] coords={c!s:10s} {s.get('description', '')[:50]}")
