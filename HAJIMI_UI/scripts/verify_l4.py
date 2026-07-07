# [VERIFY] 验收脚本 — 见 docs/FILE-MAP.md
# 用途: L4 Vision 快路径（配置 / health / LLM 烟测 / process）
# 运行: python scripts/verify_l4.py  （可选 --smoke）
"""
L4 Vision 快路径自动化验证。

用法:
  python scripts/verify_l4.py           # 完整验证（含 LLM 烟测 + process 联调）
  python scripts/verify_l4.py --quick   # 跳过 LLM/process（仅配置与健康检查）
  python scripts/verify_l4.py --no-llm  # 跳过 LLM 烟测，仍尝试 process
  python scripts/verify_l4.py --no-start  # 不自动启动 A 端

退出码: 0=全部通过, 1=有失败项
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


class CheckResult:
    def __init__(self, name: str, status: str, detail: str = ""):
        self.name = name
        self.status = status
        self.detail = detail


results: list[CheckResult] = []


def record(name: str, ok: bool, detail: str = "", *, skip: bool = False) -> bool:
    status = SKIP if skip else (PASS if ok else FAIL)
    results.append(CheckResult(name, status, detail))
    tag = {"PASS": "[OK]", "FAIL": "[!!]", "SKIP": "[--]"}[status]
    line = f"{tag} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def _fetch_json(url: str, timeout: float = 10.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def check_pytest() -> bool:
    print("\n=== 1. 单元测试 ===")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "server/tests/test_llm_wire.py",
        "server/tests/test_l4.py",
        "server/tests/test_l4_settings.py",
        "server/tests/test_preflight.py",
        "core/tests/test_overlay_coords.py",
        "core/tests/test_step_advance_progress.py",
        "-q",
        "--tb=no",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    detail = proc.stdout.strip().split("\n")[-1] if proc.stdout else proc.stderr[:200]
    return record("pytest (L4/wire/preflight)", ok, detail)


def check_env_config() -> bool:
    print("\n=== 2. server/.env 配置 ===")
    env_path = ROOT / "server" / ".env"
    if not env_path.is_file():
        return record("server/.env 存在", False, "缺少 server/.env")

    text = env_path.read_text(encoding="utf-8")
    ok = True

    def env_val(key: str) -> str:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
        return ""

    locator_hints = ("gpt",)

    checks = {
        "ROUTING_MODE": ("fast", "auto", "balanced"),
        "LLM_WIRE_API": ("responses",),
        "LLM_BASE_URL": ("daseinai",),
        "LLM_MODEL": ("gpt",),
    }
    for key, hints in checks.items():
        val = env_val(key).lower()
        if not val:
            record(f"{key}", False, "未设置")
            ok = False
            continue
        if key == "ROUTING_MODE" and val not in hints:
            record(key, False, f"={val}，L4 需 fast/auto/balanced")
            ok = False
        elif key == "LLM_WIRE_API" and val != "responses":
            record(key, False, f"={val}，daseinai 需 responses")
            ok = False
        elif key != "ROUTING_MODE" and key != "LLM_WIRE_API":
            if not any(h in val for h in hints):
                record(key, False, f"={env_val(key)}")
                ok = False
            else:
                record(key, True, env_val(key))
        else:
            record(key, True, env_val(key))

    if not env_val("LLM_API_KEY"):
        record("LLM_API_KEY", False, "未设置")
        ok = False
    else:
        record("LLM_API_KEY", True, "已设置（已隐藏）")

    locator_val = env_val("L4_LOCATOR_MODEL")
    if not locator_val:
        fallback = env_val("LLM_MODEL")
        if fallback and any(h in fallback.lower() for h in locator_hints):
            record(
                "L4_LOCATOR_MODEL",
                True,
                f"未设置，回退 LLM_MODEL={fallback}",
            )
        else:
            record(
                "L4_LOCATOR_MODEL",
                False,
                "未设置且无可用 LLM_MODEL 回退",
            )
            ok = False
    elif not any(h in locator_val.lower() for h in locator_hints):
        record("L4_LOCATOR_MODEL", False, f"={locator_val}")
        ok = False
    else:
        record("L4_LOCATOR_MODEL", True, locator_val)

    return ok


def _health_live_ok(base: str) -> bool:
    live = _fetch_json(f"{base}/api/demo/health/live", timeout=3)
    return bool(live and live.get("status") == "ok" and not live.get("_error"))


def ensure_a_end_if_needed(base: str, *, allow_start: bool) -> bool:
    print("\n=== 3. A 端启动检查 ===")
    if _health_live_ok(base):
        return record("A 端已运行", True, base)

    if not allow_start:
        return record(
            "A 端已运行",
            False,
            "端口未监听。请先运行 scripts\\start_l4_demo.bat，"
            "或去掉 --no-start 让脚本自动启动",
        )

    print("[..] A 端未监听，正在自动启动（新窗口 HAJIMI-A-end）…")
    try:
        from core.user_settings import apply_user_settings
        from core.service_manager import ensure_a_end_running

        apply_user_settings()
        ok = ensure_a_end_running(wait_timeout=60.0)
        if ok and _health_live_ok(base):
            return record(
                "自动启动 A 端",
                True,
                "已就绪，继续 health/process 检查",
            )
        return record(
            "自动启动 A 端",
            False,
            "超时或仍未响应。请查看 HAJIMI-A-end 窗口是否有报错",
        )
    except Exception as exc:
        return record("自动启动 A 端", False, str(exc))


def check_a_end_health(base: str) -> bool:
    print("\n=== 4. A 端健康检查 ===")
    ok = True

    if _health_live_ok(base):
        record("GET /health/live", True)
    else:
        record("GET /health/live", False, "A 端未响应")
        return False

    health = _fetch_json(f"{base}/api/demo/health", timeout=15)
    if not health or health.get("status") != "ok":
        record("GET /health", False, str(health))
        return False

    record("GET /health", True)
    for key, expected in (
        ("routing_mode", ("fast", "auto", "balanced")),
        ("llm_configured", (True,)),
        ("l4_capable", (True,)),
    ):
        val = health.get(key)
        if val in expected or (key == "routing_mode" and val in expected):
            record(f"health.{key}", True, str(val))
        else:
            record(f"health.{key}", False, f"got {val!r}, expect {expected}")
            ok = False

    if health.get("omniparser_ready") is False:
        record(
            "health.omniparser_ready",
            True,
            "false（L4 模式正常，无需 OmniParser）",
        )
    return ok


def check_b_end_preflight() -> bool:
    print("\n=== 5. B 端 L4 预检 ===")
    from core.api_client import check_process_preflight
    from core.user_settings import apply_user_settings

    apply_user_settings()
    ok, msg = check_process_preflight()
    return record("check_process_preflight()", ok, msg or "A 端 + LLM 就绪")


def check_llm_wire_smoke() -> bool:
    print("\n=== 6. LLM Responses API 烟测 ===")
    try:
        from server.config import reload_settings, settings
        from server.services.llm.wire import post_llm, resolve_wire_api

        reload_settings()
        api_key = settings.LLM_API_KEY
        base_url = (settings.LLM_BASE_URL or "").rstrip("/")
        model = settings.LLM_MODEL or "gpt-5.5"
        wire = resolve_wire_api(base_url)

        if not api_key or not base_url:
            return record("LLM 烟测", False, "LLM_API_KEY 或 LLM_BASE_URL 未配置")

        record("resolve_wire_api", wire == "responses", f"wire={wire}")

        text, usage = post_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system="Reply with exactly: OK",
            user="ping",
            max_tokens=16,
            timeout=30.0,
            wire_api=wire,
        )
        ok = bool(text.strip())
        return record(
            f"POST {base_url}/responses",
            ok,
            f"model={model}, reply={text.strip()[:80]!r}, usage={usage}",
        )
    except Exception as exc:
        return record("LLM 烟测", False, str(exc))


def check_l4_planner_inprocess() -> bool:
    print("\n=== 7. L4 Planner 进程内联调 ===")
    try:
        from server.config import reload_settings

        reload_settings()
        from server.services.l4.planner import plan_l4_steps

        steps, meta = plan_l4_steps(
            "导出当前文档为PDF",
            image_b64=None,
        )
        ok = len(steps) >= 1
        return record(
            "plan_l4_steps()",
            ok,
            f"steps={len(steps)}, model={meta.get('model')}, "
            f"wire={meta.get('wire_api')}, latency={meta.get('latency_ms')}ms",
        )
    except Exception as exc:
        return record("plan_l4_steps()", False, str(exc))


def check_process_l4(base: str) -> bool:
    print("\n=== 8. L4 process HTTP 联调 ===")
    from config import DEMO_KEY

    payload = {
        # 避开 L2 模板命中（带截图时会强制 L3 OmniParser）
        "query": "导出当前文档为PDF",
        "image": TINY_PNG,
        "window_title": "桌面",
        "context": [],
        "capture_size": [1920, 1080],
        "upload_size": [1, 1],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/demo/process",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Demo-Key": DEMO_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:500]
        return record("POST /process", False, f"HTTP {exc.code}: {err}")
    except Exception as exc:
        return record("POST /process", False, str(exc))

    if not body.get("success"):
        redline = body.get("redline") or {}
        return record(
            "POST /process",
            False,
            redline.get("message") or "success=false",
        )

    meta = body.get("detection_meta") or {}
    route = meta.get("route", "?")
    steps = body.get("steps") or []
    ok = route == "L4" and len(steps) > 0
    detail = (
        f"route={route}, steps={len(steps)}, "
        f"task_id={str(body.get('task_id', ''))[:8]}..."
    )
    if route != "L4":
        detail += (
            " (若 query 命中 L2 模板会走 L3；本脚本已用无模板 query。"
            f" meta={meta})"
        )
    return record("POST /process (L4)", ok, detail)


def check_l4_real_screen_locate(*, skip: bool = False) -> bool:
    """可选：真实屏幕 L4 Locator 烟测（需 LLM 计费）。"""
    print("\n=== 8. 真实屏幕 L4 定位（可选） ===")
    if skip:
        return record("diagnose_l4_locate", True, "已跳过", skip=True)

    import importlib.util

    path = ROOT / "scripts" / "diagnose_l4_locate.py"
    spec = importlib.util.spec_from_file_location("diagnose_l4_locate", path)
    if spec is None or spec.loader is None:
        return record("diagnose_l4_locate (real screen)", False, "无法加载诊断脚本")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    try:
        report = mod.run_diagnose("点击任务栏上的开始按钮")
        ok = bool(report.get("has_point"))
        detail = (
            f"latency={report.get('latency_ms')}ms "
            f"raw={str(report.get('raw_locator_output', ''))[:80]!r}"
        )
        return record("diagnose_l4_locate (real screen)", ok, detail)
    except Exception as exc:
        return record("diagnose_l4_locate (real screen)", False, str(exc))


def summarize() -> int:
    print("\n=== 汇总 ===")
    passed = sum(1 for r in results if r.status == PASS)
    failed = sum(1 for r in results if r.status == FAIL)
    skipped = sum(1 for r in results if r.status == SKIP)
    print(f"通过 {passed} | 失败 {failed} | 跳过 {skipped} | 共 {len(results)}")

    if failed:
        print("\n失败项:")
        for r in results:
            if r.status == FAIL:
                print(f"  - {r.name}: {r.detail}")
        return 1
    print("\n[OK] L4 自动化验证全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="L4 Vision 自动化验证")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="仅单元测试 + 配置 + 健康 + 预检",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="跳过 LLM 烟测",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="A 端未运行时不要自动启动",
    )
    parser.add_argument(
        "--locate-real-screen",
        action="store_true",
        help="额外运行真实屏幕 L4 Locator 诊断（需 LLM 计费）",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("HAJIMI_API_URL", "http://127.0.0.1:8010"),
        help="A 端地址",
    )
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print("=== HAJIMI L4 自动化验证 ===")
    print(f"A 端: {base}\n")

    all_ok = True
    all_ok &= check_pytest()
    all_ok &= check_env_config()
    all_ok &= ensure_a_end_if_needed(base, allow_start=not args.no_start)
    all_ok &= check_a_end_health(base)
    all_ok &= check_b_end_preflight()

    if not args.quick:
        if not args.no_llm:
            all_ok &= check_llm_wire_smoke()
        all_ok &= check_l4_planner_inprocess()
        all_ok &= check_process_l4(base)
        if args.locate_real_screen:
            all_ok &= check_l4_real_screen_locate()

    if not all_ok and any(r.status == FAIL for r in results):
        pass  # summarize will exit 1

    return summarize()


if __name__ == "__main__":
    sys.exit(main())
