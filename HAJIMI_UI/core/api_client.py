import json
import urllib.error
import urllib.request
from typing import List, Optional

from config import API_BASE_URL, DEMO_KEY, USE_MOCK_ONLY
from core.mock_backend import advance_step as mock_advance_step
from core.mock_backend import process_query, register_task


def process(query: str, image_data_uri: str, window_title: str = "桌面",
            screen_width: int = 1920, screen_height: int = 1080) -> dict:
    if USE_MOCK_ONLY:
        mock = process_query(query, screen_width, screen_height)
        if mock:
            return mock
        raise ValueError("Mock 未匹配到该问题，请尝试输入「怎么安装微信」")

    payload = json.dumps({
        "query": query,
        "image": image_data_uri,
        "window_title": window_title,
        "context": [],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE_URL}/api/demo/process",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Demo-Key": DEMO_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("task_id") and data.get("steps"):
                register_task(data["task_id"], data["steps"])
            return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"[API] 后端不可用 ({exc})，回退 Mock")
        mock = process_query(query, screen_width, screen_height)
        if mock:
            return mock
        raise ValueError("后端不可用且 Mock 未匹配，请尝试「怎么安装微信」") from exc


def advance_step(
    task_id: str,
    step_index: int,
    fingerprint: str = "",
    action: str = "advance",
    steps: Optional[List[dict]] = None,
) -> dict:
    if USE_MOCK_ONLY:
        return mock_advance_step(task_id, step_index, fingerprint, action, steps)

    payload = json.dumps({
        "task_id": task_id,
        "action": action,
        "step_index": step_index,
        "fingerprint": fingerprint or "",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE_URL}/api/demo/step",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Demo-Key": DEMO_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        print(f"[API] step 后端不可用 ({exc})，回退 Mock")
        return mock_advance_step(task_id, step_index, fingerprint, action, steps)
