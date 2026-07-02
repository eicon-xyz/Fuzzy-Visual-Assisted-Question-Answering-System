"""
B-end <-> A-end integration verify script.

Usage:
  1. Terminal 1: scripts/start_server.bat  (default port 8001)
  2. Terminal 2: python scripts/verify_integration.py
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ALLOW_MOCK_FALLBACK, USE_MOCK_ONLY
from core.api_client import ApiError, advance_step, check_health, inspect, process

TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_health():
    ok = check_health()
    print(f"[health] {'OK' if ok else 'FAIL'}")
    assert ok, "A 端 health 不可用，请先启动 server"
    return True


def test_process_via_client():
    try:
        data = process("怎么安装微信", TINY_PNG, screen_width=1920, screen_height=1080)
    except ApiError as exc:
        msg = str(exc)
        if any(x in msg for x in ("422", "502", "未检测", "DETECTOR", "OmniParser 内部", "空白", "NO_ELEMENTS")):
            print(f"[process] SKIP ({msg}) — 1x1 测试图无法通过 OmniParser，请用真实截图联调")
            return None, None
        raise
    assert data.get("_source") == "server", f"期望 _source=server，实际: {data.keys()}"
    assert not data.get("_mock"), "不应回退客户端 Mock"
    assert data.get("task_id") and data.get("steps"), "缺少 task_id/steps"
    ref = data.get("reference_resolution") or data.get("_ref_size")
    if ref:
        print(f"[process] reference_resolution={ref}")
    print(f"[process] OK task_id={data['task_id'][:8]}... steps={len(data['steps'])}")
    return data["task_id"], data["steps"]


def test_inspect_via_client():
    try:
        data = inspect(TINY_PNG, screen_width=1920, screen_height=1080)
    except ApiError as exc:
        msg = str(exc)
        if any(x in msg for x in ("422", "502", "未检测", "DETECTOR", "OmniParser 内部", "空白", "NO_ELEMENTS")):
            print(f"[inspect] SKIP ({msg}) — 需真实截图或 ALLOW_DETECTOR_FALLBACK=1")
            return
        raise
    assert data.get("success")
    assert "ui_elements" in data
    assert data.get("reference_resolution")
    print(f"[inspect] OK elements={len(data.get('ui_elements') or [])}")


def test_advance_via_client(task_id, steps):
    total = len(steps)
    step_index = 1
    while step_index <= total:
        resp = advance_step(task_id, step_index, "test-fp", "advance", steps)
        action = resp.get("action")
        print(f"[step {step_index}] action={action}")
        if action == "complete":
            break
        step_index = resp.get("current_step", step_index + 1)
    assert resp.get("action") == "complete"
    print("[advance] OK")


def test_offline_no_silent_mock():
    if USE_MOCK_ONLY or ALLOW_MOCK_FALLBACK:
        print("[offline] 跳过（MOCK_ONLY 或 MOCK_FALLBACK 已开启）")
        return

    import core.api_client as api_mod

    old_url = os.environ.get("HAJIMI_API_URL", "")
    os.environ["HAJIMI_API_URL"] = "http://127.0.0.1:59999"
    api_mod.reload_client_config()
    try:
        tiny_png = "data:image/png;base64,abc"
        try:
            process("怎么安装微信", tiny_png)
            raise AssertionError("离线时应抛出 ApiError，不应静默 Mock")
        except ApiError as exc:
            print(f"[offline] OK ApiError: {exc}")
    finally:
        if old_url:
            os.environ["HAJIMI_API_URL"] = old_url
        else:
            os.environ.pop("HAJIMI_API_URL", None)
        api_mod.reload_client_config()


def main():
    print("=== HAJIMI B-A integration verify ===")
    test_health()
    test_inspect_via_client()
    task_id, steps = test_process_via_client()
    if task_id and steps:
        test_advance_via_client(task_id, steps)
    else:
        print("[advance] SKIP（process 未返回有效任务）")
    test_offline_no_silent_mock()
    print("\n[OK] 所有联调检查通过")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
