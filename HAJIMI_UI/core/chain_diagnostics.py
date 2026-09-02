"""Full-chain diagnostics for inspect / GPU API deployment."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import API_BASE_URL, SERVER_DEFAULT_PORT
from core.defaults import (
    DEFAULT_DEPLOYMENT_MODE,
    DEFAULT_OMNI_GPU_API_URL,
    DEFAULT_OMNI_LOCAL_URL,
)
from core.env_sync import ENV_PATH
from core.user_settings import load_user_settings

TINY_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
LOCAL_CPU_URL = DEFAULT_OMNI_LOCAL_URL
_PROBE_B64_CACHE: Optional[str] = None
PROBE_WIDTH = 960
PROBE_HEIGHT = 540


def _probe_image_b64() -> str:
    """960×540 synthetic UI PNG for GPU parse / e2e probes."""
    global _PROBE_B64_CACHE
    if _PROBE_B64_CACHE:
        return _PROBE_B64_CACHE
    try:
        import base64
        import io

        from PIL import Image, ImageDraw

        w, h = PROBE_WIDTH, PROBE_HEIGHT
        img = Image.new("RGB", (w, h), (245, 245, 248))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, w, 48], fill=(45, 45, 55))
        draw.text((16, 14), "Download Center", fill=(255, 255, 255))
        draw.rectangle([300, 180, 660, 250], fill=(66, 133, 244))
        draw.text((430, 200), "Download", fill=(255, 255, 255))
        draw.rectangle([300, 290, 660, 350], fill=(255, 255, 255), outline=(180, 180, 190))
        draw.text((316, 308), "Password", fill=(120, 120, 130))
        draw.rectangle([300, 380, 480, 440], fill=(52, 168, 83))
        draw.text((340, 398), "Sign in", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _PROBE_B64_CACHE = base64.b64encode(buf.getvalue()).decode("ascii")
        return _PROBE_B64_CACHE
    except Exception:
        return TINY_B64


def _parse_error_detail(resp) -> str:
    """Extract error code/message from OmniParser HTTP response body."""
    try:
        body = resp.json()
        err = body.get("error")
        if isinstance(err, dict):
            code = err.get("code") or err.get("type") or ""
            msg = err.get("message") or err.get("detail") or str(err)
            return f"HTTP {resp.status_code} {code}: {msg}".strip()
        if isinstance(err, str):
            return f"HTTP {resp.status_code}: {err}"
        detail = body.get("detail")
        if detail:
            return f"HTTP {resp.status_code}: {detail}"
    except Exception:
        pass
    text = (resp.text or "")[:300]
    return f"HTTP {resp.status_code}: {text or resp.reason_phrase}"


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _get_json(url: str, timeout: float = 5.0) -> tuple[bool, Any, int]:
    t0 = time.perf_counter()
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            latency = int((time.perf_counter() - t0) * 1000)
            return True, json.loads(body), latency
    except URLError as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, str(getattr(exc, "reason", exc)), latency
    except Exception as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, str(exc), latency


def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> tuple[bool, int]:
    t0 = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        latency = int((time.perf_counter() - t0) * 1000)
        return True, latency
    except OSError:
        latency = int((time.perf_counter() - t0) * 1000)
        return False, latency
    finally:
        sock.close()


def _port_listeners(port: int) -> List[int]:
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return []
    pids: List[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            try:
                pids.append(int(parts[-1]))
            except ValueError:
                pass
    return pids


def _expected_omni_url(mode: str, user_data: dict) -> str:
    omni = user_data.get("omniparser") or {}
    if omni.get("url"):
        return _normalize_url(str(omni["url"]))
    if mode == "gpu_api":
        return _normalize_url(DEFAULT_OMNI_GPU_API_URL)
    return _normalize_url(DEFAULT_OMNI_LOCAL_URL)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    latency_ms: Optional[int] = None
    data: Optional[Any] = None


@dataclass
class ChainDiagnosticReport:
    timestamp: str
    deployment_mode: str
    expected_omni_url: str
    config: Dict[str, Any] = field(default_factory=dict)
    url_consistency: Dict[str, str] = field(default_factory=dict)
    checks: List[CheckResult] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    latency_summary: Dict[str, Any] = field(default_factory=dict)
    billing_note: str = ""
    overall_ok: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _real_screen_b64() -> tuple[str, str, int, int]:
    """Capture desktop, downscale for fast upload; returns (b64, detail, w, h)."""
    from core.screen_utils import capture_screen, downscale_for_api, pil_to_data_uri

    img = capture_screen()
    if img is None:
        raise RuntimeError("screen capture failed")
    ow, oh = img.size
    small = downscale_for_api(img, 720)
    sw, sh = small.size
    uri = pil_to_data_uri(small, quality=82)
    b64 = uri.split(",", 1)[1] if "," in uri else uri
    detail = f"capture={ow}x{oh} sent={sw}x{sh}"
    return b64, detail, sw, sh


def _post_parse_with_b64(
    url: str,
    b64: str,
    *,
    name: str,
    image_detail: str,
    timeout: float = 35.0,
) -> CheckResult:
    import httpx

    base = _normalize_url(url)
    t0 = time.perf_counter()
    last_detail = "no compatible /parse endpoint"
    try:
        with httpx.Client(timeout=timeout) as client:
            for endpoint in (f"{base}/parse/", f"{base}/parse"):
                resp = client.post(endpoint, json={"base64_image": b64})
                if resp.status_code in (404, 405):
                    continue
                if resp.status_code in (422, 400, 502):
                    last_detail = _parse_error_detail(resp)
                    continue
                resp.raise_for_status()
                payload = resp.json()
                n = len(payload.get("parsed_content_list") or [])
                latency = int((time.perf_counter() - t0) * 1000)
                device = payload.get("device", "?")
                return CheckResult(
                    name=name,
                    ok=True,
                    detail=f"elements={n} device={device} {image_detail}",
                    latency_ms=latency,
                    data={"element_count": n, "device": device},
                )
        latency = int((time.perf_counter() - t0) * 1000)
        return CheckResult(
            name=name, ok=False, detail=last_detail, latency_ms=latency
        )
    except Exception as exc:
        latency = int((time.perf_counter() - t0) * 1000)
        return CheckResult(name=name, ok=False, detail=str(exc), latency_ms=latency)


def _post_parse(url: str, timeout: float = 120.0) -> CheckResult:
    b64 = _probe_image_b64()
    return _post_parse_with_b64(
        url,
        b64,
        name=f"parse_probe ({_normalize_url(url)})",
        image_detail=f"image={PROBE_WIDTH}x{PROBE_HEIGHT}",
        timeout=timeout,
    )


def _probe_llm() -> CheckResult:
    try:
        from server.services.llm.client import probe_llm_chat

        ok, detail, latency = probe_llm_chat(timeout=15.0)
        return CheckResult(
            name="LLM API probe (OpenAI)",
            ok=ok,
            detail=detail + (" (会产生少量计费)" if ok else ""),
            latency_ms=latency,
        )
    except Exception as exc:
        return CheckResult("LLM API probe (OpenAI)", False, str(exc), 0)


def _analyze_issues(
    report: ChainDiagnosticReport,
    mode: str,
    expected: str,
    a_end_omni: str,
    server_env_url: str,
) -> None:
    issues = report.issues
    recs = report.recommendations

    if mode == "gpu_api":
        if a_end_omni and a_end_omni != expected:
            issues.append(
                f"URL 不一致：A 端={a_end_omni}，设置/期望={expected}"
            )
            recs.append("保存设置后点击「启动 A 端」或运行 scripts\\start_server.bat 重启 A 端")
        if server_env_url and server_env_url != expected:
            issues.append(
                f"server/.env OMNIPARSER_URL={server_env_url} 与期望 {expected} 不一致"
            )
            recs.append("在设置页保存一次以同步 server/.env，然后重启 A 端")
        if ":8002" in a_end_omni:
            issues.append("A 端仍指向本地 CPU :8002，GPU API 模式会极慢或超时")
            recs.append("确认 server/.env 中 OMNIPARSER_URL=http://127.0.0.1:9800 并重启 A 端")
        port_8002 = next(
            (c for c in report.checks if c.name == "port :8002 (local CPU legacy)"),
            None,
        )
        if port_8002 and (port_8002.data or {}).get("listening"):
            issues.append("本地 :8002 OmniParser 仍在运行，可能与 GPU 模式混淆")
            recs.append("GPU API 模式下可 scripts\\stop_all.bat 停止 :8002，避免误连 CPU")

    for check in report.checks:
        if check.name.startswith("gpu_health [expected]") and not check.ok:
            issues.append(f"GPU OmniParser 不可达: {check.detail}")
            recs.append("运行根目录 启动HAJIMI.bat 或 scripts\\start_release_fullstack.bat")
        if check.name == "A-end /health/live" and not check.ok:
            issues.append(f"A 端 event loop 阻塞或崩溃: {check.detail}")
            recs.append("重启 A 端 scripts\\start_server.bat；避免并发多次检测")
        if check.name == "A-end /health" and not check.ok:
            issues.append(f"A 端 health 不可达: {check.detail}")
            recs.append("设置页点击「启动 A 端」或 scripts\\start_server.bat")
        elif check.name == "A-end /health" and check.ok and (check.latency_ms or 0) > 3000:
            issues.append(
                f"A 端 /health 响应过慢 ({check.latency_ms}ms)，可能 event loop 被阻塞"
            )
            recs.append("重启 A 端；确保已应用 asyncio.to_thread 修复")
        if check.name.startswith("parse_probe") and not check.ok and mode == "gpu_api":
            gpu_ok = any(
                c.ok and c.name.startswith("gpu_health [expected]")
                for c in report.checks
            )
            if gpu_ok:
                issues.append(f"Parse 探针失败（探针图无效或客户端过旧）: {check.detail}")
                recs.append("更新 B 端客户端后重试链路诊断；GPU 服务本身可能正常")
            else:
                issues.append(f"Parse 探针失败: {check.detail}")
                recs.append(
                    "确认远程 GPU 上 omniparser_api 已启动 (local_vision 模式（GPU 隧道已移除）)"
                )
        if check.name == "LLM API probe (OpenAI)" and not check.ok:
            issues.append(f"OpenAI LLM 不可达: {check.detail}")
            recs.append("检查 server/.env 中 LLM_API_KEY、LLM_BASE_URL 与网络")

    llm_base = (report.config.get("server_env") or {}).get("LLM_BASE_URL") or ""
    if llm_base and "api.openai.com" in llm_base:
        issues.append(
            f"LLM_BASE_URL 指向官方 OpenAI ({llm_base})，中转站 key 会超时；"
            "应改为 https://www.daseinai.xyz/v1 并重启 A 端"
        )
        recs.append("运行 python scripts/sync_llm_from_env.py 或手动修正 server/.env")

    real_check = next(
        (c for c in report.checks if c.name.startswith("parse_real_screen")), None
    )
    probe_check = next(
        (c for c in report.checks if c.name.startswith("parse_probe")), None
    )
    if (
        real_check
        and probe_check
        and real_check.latency_ms is not None
        and probe_check.latency_ms is not None
        and probe_check.ok
        and real_check.latency_ms > max(5000, probe_check.latency_ms * 10)
    ):
        issues.append(
            f"实屏 parse ({real_check.latency_ms}ms) 远慢于探针 "
            f"({probe_check.latency_ms}ms)，GPU 对真实桌面截图异常"
        )
        recs.append(
            "重启 GPU 隧道（启动HAJIMI.bat）；L2 模板问题可跳过 parse；"
            "L3 将走 parse 超时后纯文本降级"
        )
    l2_check = next(
        (c for c in report.checks if c.name.startswith("L2 skip parse")), None
    )
    if l2_check and not l2_check.ok:
        issues.append(f"L2 未跳过 parse: {l2_check.detail}")
        recs.append("重启 A 端 scripts\\start_server.bat 以加载最新 router")


def run_full_diagnostic(
    *,
    include_parse: bool = False,
    include_e2e_inspect: bool = False,
    include_e2e_process: bool = False,
    include_llm: bool = False,
    include_fast_assert: bool = False,
    include_real_screen: bool = False,
    include_l2_assert: bool = False,
) -> ChainDiagnosticReport:
    user_data = load_user_settings()
    mode = user_data.get("deployment_mode", DEFAULT_DEPLOYMENT_MODE)
    expected = _expected_omni_url(mode, user_data)
    server_env = _parse_env_file(ENV_PATH)
    server_env_url = _normalize_url(server_env.get("OMNIPARSER_URL", ""))

    report = ChainDiagnosticReport(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        deployment_mode=mode,
        expected_omni_url=expected,
        config={
            "user_settings": {
                "deployment_mode": mode,
                "omniparser_url": (user_data.get("omniparser") or {}).get("url"),
                "a_end_url": user_data.get("a_end_url"),
            },
            "server_env": {
                "OMNIPARSER_URL": server_env.get("OMNIPARSER_URL"),
                "OMNIPARSER_TIMEOUT": server_env.get("OMNIPARSER_TIMEOUT"),
                "LLM_BASE_URL": server_env.get("LLM_BASE_URL"),
                "LLM_MODEL": server_env.get("LLM_MODEL"),
                "LLM_SPEED_MODE": server_env.get("LLM_SPEED_MODE", "fast"),
                "path": str(ENV_PATH),
                "exists": ENV_PATH.is_file(),
            },
            "b_end_env": {
                "HAJIMI_DEPLOYMENT_MODE": os.environ.get("HAJIMI_DEPLOYMENT_MODE"),
                "OMNIPARSER_URL": os.environ.get("OMNIPARSER_URL"),
                "HAJIMI_API_URL": os.environ.get("HAJIMI_API_URL", API_BASE_URL),
            },
            "api_base_url": API_BASE_URL,
        },
    )

    a_end_omni = ""
    a_health_data: Optional[dict] = None

    ok_live, live_data, live_ms = _get_json(
        f"{API_BASE_URL}/api/demo/health/live", timeout=2.0
    )
    if ok_live:
        detail = "alive"
        if live_ms > 500:
            detail += f" SLOW ({live_ms}ms)"
        report.checks.append(
            CheckResult("A-end /health/live", True, detail, live_ms, live_data)
        )
    else:
        report.checks.append(
            CheckResult("A-end /health/live", False, str(live_data), live_ms)
        )

    ok, data, latency = _get_json(f"{API_BASE_URL}/api/demo/health", timeout=8.0)
    if ok and isinstance(data, dict):
        a_health_data = data
        a_end_omni = _normalize_url(data.get("omniparser_url") or "")
        ready = data.get("omniparser_ready")
        device = data.get("detector_device")
        detail = (
            f"omniparser_url={a_end_omni} ready={ready} device={device} "
            f"config_source={data.get('config_source', '?')}"
        )
        report.checks.append(
            CheckResult("A-end /health", True, detail, latency, data)
        )
    else:
        report.checks.append(
            CheckResult("A-end /health", False, str(data), latency)
        )

    report.url_consistency = {
        "expected": expected,
        "server_env": server_env_url or "(missing)",
        "a_end_health": a_end_omni or "(unreachable)",
        "match_settings_vs_a_end": str(a_end_omni == expected) if a_end_omni else "unknown",
        "match_settings_vs_env": str(server_env_url == expected) if server_env_url else "unknown",
    }

    for port, label in (
        (SERVER_DEFAULT_PORT, "A-end"),
        (9800, "GPU tunnel"),
        (8002, "local CPU legacy"),
    ):
        tcp_ok, tcp_ms = _probe_tcp("127.0.0.1", port)
        pids = _port_listeners(port)
        pid_text = f"PID={pids}" if pids else "no LISTENING"
        check_ok = tcp_ok
        detail = f"tcp={'ok' if tcp_ok else 'fail'} {pid_text}"
        if port == 8002 and mode == "gpu_api" and not tcp_ok:
            check_ok = True
            detail = f"optional, not required ({pid_text})"
        report.checks.append(
            CheckResult(
                f"port :{port} ({label})",
                check_ok,
                detail,
                tcp_ms,
                {"pids": pids, "listening": tcp_ok},
            )
        )

    probe_urls: List[tuple[str, str]] = [(expected, "expected")]
    if a_end_omni and a_end_omni != expected:
        probe_urls.append((a_end_omni, "a_end_actual"))
    if mode == "gpu_api" and LOCAL_CPU_URL not in [u for u, _ in probe_urls]:
        probe_urls.append((LOCAL_CPU_URL, "local_cpu_legacy"))

    for url, tag in probe_urls:
        ok, data, latency = _get_json(f"{url}/health")
        if ok and isinstance(data, dict):
            ready = data.get("ready", data.get("status") == "ok")
            device = data.get("device", "?")
            detail = f"ready={ready} device={device}"
            report.checks.append(
                CheckResult(
                    f"gpu_health [{tag}] ({url})",
                    bool(ready),
                    detail,
                    latency,
                    data,
                )
            )
        else:
            ok2, data2, latency2 = _get_json(f"{url}/probe/")
            if ok2:
                report.checks.append(
                    CheckResult(
                        f"omni_probe [{tag}] ({url})",
                        True,
                        str(data2)[:200],
                        latency2,
                        data2 if isinstance(data2, dict) else None,
                    )
                )
            else:
                if tag == "local_cpu_legacy" and mode == "gpu_api":
                    report.checks.append(
                        CheckResult(
                            f"gpu_health [{tag}] ({url})",
                            True,
                            f"optional legacy not running ({data})",
                            latency,
                        )
                    )
                else:
                    report.checks.append(
                        CheckResult(
                            f"gpu_health [{tag}] ({url})",
                            False,
                            str(data),
                            latency,
                        )
                    )

    if include_llm:
        report.checks.append(_probe_llm())

    if include_parse:
        parse_url = a_end_omni or expected
        report.checks.append(_post_parse(parse_url, timeout=120.0 if mode != "gpu_api" else 30.0))

    if include_real_screen:
        parse_url = a_end_omni or expected
        try:
            b64, img_detail, _, _ = _real_screen_b64()
            report.checks.append(
                _post_parse_with_b64(
                    parse_url,
                    b64,
                    name=f"parse_real_screen ({parse_url})",
                    image_detail=img_detail,
                    timeout=35.0,
                )
            )
        except Exception as exc:
            report.checks.append(
                CheckResult(
                    f"parse_real_screen ({parse_url})",
                    False,
                    str(exc),
                    0,
                )
            )

    if include_l2_assert and a_health_data:
        import httpx

        from config import DEMO_KEY

        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{API_BASE_URL}/api/demo/process",
                    headers={"X-Demo-Key": DEMO_KEY},
                    json={
                        "query": "怎么截屏",
                        "image": f"data:image/png;base64,{_probe_image_b64()}",
                        "window_title": "桌面",
                    },
                )
            latency = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                meta = resp.json().get("detection_meta") or {}
                skipped = meta.get("parse_skipped") is True
                report.checks.append(
                    CheckResult(
                        "L2 skip parse (/process 怎么截屏)",
                        skipped and latency < 5000,
                        f"parse_skipped={meta.get('parse_skipped')} "
                        f"route={meta.get('route')} parse_ms={meta.get('parse_latency_ms')} "
                        f"total_ms={latency}",
                        latency,
                        meta,
                    )
                )
            else:
                report.checks.append(
                    CheckResult(
                        "L2 skip parse (/process 怎么截屏)",
                        False,
                        f"HTTP {resp.status_code}",
                        latency,
                    )
                )
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            report.checks.append(
                CheckResult(
                    "L2 skip parse (/process 怎么截屏)", False, str(exc), latency
                )
            )

    if include_e2e_inspect and a_health_data:
        import httpx

        from config import DEMO_KEY

        t0 = time.perf_counter()
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{API_BASE_URL}/api/demo/inspect",
                    headers={"X-Demo-Key": DEMO_KEY},
                    json={
                        "image": f"data:image/png;base64,{_probe_image_b64()}",
                        "screen_width": PROBE_WIDTH,
                        "screen_height": PROBE_HEIGHT,
                    },
                )
            latency = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                payload = resp.json()
                n = len(payload.get("ui_elements") or [])
                meta = payload.get("detection_meta") or {}
                parse_ms = meta.get("parse_latency_ms") or meta.get("latency_ms")
                report.checks.append(
                    CheckResult(
                        "e2e A-end /inspect (无 OpenAI 计费)",
                        payload.get("success", True),
                        f"elements={n} device={meta.get('device')} "
                        f"parse_ms={parse_ms} url={meta.get('omniparser_url')}",
                        latency,
                        meta,
                    )
                )
            else:
                report.checks.append(
                    CheckResult(
                        "e2e A-end /inspect (无 OpenAI 计费)",
                        False,
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        latency,
                    )
                )
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            report.checks.append(
                CheckResult(
                    "e2e A-end /inspect (无 OpenAI 计费)", False, str(exc), latency
                )
            )

    if include_e2e_process and a_health_data:
        import httpx

        from config import DEMO_KEY

        t0 = time.perf_counter()
        complex_query = (
            "请帮我在浏览器里下载安装微信并完成登录配置，需要跨多个步骤操作"
        )
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{API_BASE_URL}/api/demo/process",
                    headers={"X-Demo-Key": DEMO_KEY},
                    json={
                        "query": complex_query,
                        "image": f"data:image/png;base64,{_probe_image_b64()}",
                        "window_title": "桌面",
                        "context": [],
                    },
                )
            latency = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                payload = resp.json()
                meta = payload.get("detection_meta") or {}
                llm_called = meta.get("llm_called")
                route = meta.get("route")
                parse_ms = meta.get("parse_latency_ms") or meta.get("latency_ms")
                llm_ms = meta.get("llm_latency_ms")
                report.checks.append(
                    CheckResult(
                        "e2e A-end /process",
                        payload.get("success", True),
                        f"route={route} llm_called={llm_called} "
                        f"llm_provider={meta.get('llm_provider')} "
                        f"llm_speed_mode={meta.get('llm_speed_mode')} "
                        f"llm_used_vision={meta.get('llm_used_vision')} "
                        f"parse_ms={parse_ms} llm_ms={llm_ms} "
                        f"llm_error={meta.get('llm_error')} "
                        f"steps={len(payload.get('steps') or [])}",
                        latency,
                        meta,
                    )
                )
            else:
                report.checks.append(
                    CheckResult(
                        "e2e A-end /process",
                        False,
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        latency,
                    )
                )
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            report.checks.append(
                CheckResult("e2e A-end /process", False, str(exc), latency)
            )

    if include_fast_assert and a_health_data:
        import httpx

        from config import DEMO_KEY

        t0 = time.perf_counter()
        fast_query = "请根据当前屏幕上的元素，说明如何完成账号注册的全部步骤"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{API_BASE_URL}/api/demo/process",
                    headers={"X-Demo-Key": DEMO_KEY},
                    json={
                        "query": fast_query,
                        "image": f"data:image/png;base64,{_probe_image_b64()}",
                        "window_title": "桌面",
                        "context": [],
                    },
                )
            latency = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 200:
                payload = resp.json()
                meta = payload.get("detection_meta") or {}
                speed_mode = meta.get("llm_speed_mode", server_env.get("LLM_SPEED_MODE", "fast"))
                used_vision = meta.get("llm_used_vision")
                fast_ok = (
                    payload.get("success", True)
                    and latency < 5000
                    and used_vision is False
                    and speed_mode == "fast"
                )
                detail = (
                    f"total_ms={latency} speed_mode={speed_mode} "
                    f"llm_used_vision={used_vision} "
                    f"llm_provider={meta.get('llm_provider')} "
                    f"route={meta.get('route')}"
                )
                report.checks.append(
                    CheckResult(
                        "fast path /process (<5s)",
                        fast_ok,
                        detail,
                        latency,
                        meta,
                    )
                )
            else:
                report.checks.append(
                    CheckResult(
                        "fast path /process (<5s)",
                        False,
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        latency,
                    )
                )
        except Exception as exc:
            latency = int((time.perf_counter() - t0) * 1000)
            report.checks.append(
                CheckResult("fast path /process (<5s)", False, str(exc), latency)
            )

    _analyze_issues(report, mode, expected, a_end_omni, server_env_url)

    def _lat(name_prefix: str) -> Optional[int]:
        for c in report.checks:
            if c.name.startswith(name_prefix) and c.latency_ms is not None:
                return c.latency_ms
        return None

    llm_check = next(
        (c for c in report.checks if c.name == "LLM API probe (OpenAI)"), None
    )
    process_check = next(
        (c for c in report.checks if c.name == "e2e A-end /process"), None
    )
    inspect_check = next(
        (c for c in report.checks if c.name.startswith("e2e A-end /inspect")), None
    )
    report.latency_summary = {
        "a_end_live_ms": _lat("A-end /health/live"),
        "a_end_health_ms": _lat("A-end /health"),
        "gpu_health_ms": _lat("gpu_health [expected]"),
        "parse_ms": _lat("parse_probe"),
        "llm_probe_ms": llm_check.latency_ms if llm_check else None,
        "e2e_inspect_ms": inspect_check.latency_ms if inspect_check else None,
        "e2e_process_ms": process_check.latency_ms if process_check else None,
    }
    if inspect_check and isinstance(inspect_check.data, dict):
        report.latency_summary["e2e_inspect_parse_ms"] = (
            inspect_check.data.get("parse_latency_ms")
            or inspect_check.data.get("latency_ms")
        )
    if process_check and isinstance(process_check.data, dict):
        report.latency_summary["llm_reached"] = process_check.data.get("llm_called")
        report.latency_summary["e2e_process_parse_ms"] = (
            process_check.data.get("parse_latency_ms")
            or process_check.data.get("latency_ms")
        )
        report.latency_summary["e2e_process_llm_ms"] = process_check.data.get(
            "llm_latency_ms"
        )
    real_check = next(
        (c for c in report.checks if c.name.startswith("parse_real_screen")), None
    )
    probe_check = next(
        (c for c in report.checks if c.name.startswith("parse_probe")), None
    )
    if real_check:
        report.latency_summary["parse_real_screen_ms"] = real_check.latency_ms
    if probe_check:
        report.latency_summary["parse_probe_ms"] = probe_check.latency_ms
    if process_check and isinstance(process_check.data, dict):
        report.latency_summary["llm_speed_mode"] = process_check.data.get(
            "llm_speed_mode"
        )
        report.latency_summary["llm_used_vision"] = process_check.data.get(
            "llm_used_vision"
        )
    elif include_e2e_process:
        report.latency_summary["llm_reached"] = "unknown"
    else:
        report.latency_summary["llm_reached"] = "not_tested"

    if include_llm and llm_check and llm_check.ok:
        report.billing_note = "LLM 探针已成功 — OpenAI 控制台应出现少量用量"
    elif process_check and isinstance(process_check.data, dict):
        if process_check.data.get("llm_called"):
            report.billing_note = (
                "e2e /process 已调用 LLM"
                if not process_check.data.get("llm_error")
                else f"LLM 已尝试但失败: {process_check.data.get('llm_error')}"
            )
        else:
            report.billing_note = "e2e /process 未到达 LLM（L2 或 mock 降级）"
    else:
        report.billing_note = (
            "inspect/检测不产生 OpenAI 计费；主界面提问 /process L3 才会计费。"
            " 用量 $0 通常表示请求卡在 :8010 或 parse 阶段。"
        )
    report.overall_ok = _compute_overall_ok(
        report,
        mode=mode,
        expected=expected,
        a_end_omni=a_end_omni,
        include_parse=include_parse,
    )
    if include_fast_assert:
        fast_check = next(
            (c for c in report.checks if c.name.startswith("fast path")), None
        )
        if not fast_check or not fast_check.ok:
            report.overall_ok = False
    return report


def _compute_overall_ok(
    report: ChainDiagnosticReport,
    *,
    mode: str,
    expected: str,
    a_end_omni: str,
    include_parse: bool,
) -> bool:
    if report.issues:
        return False
    if mode == "gpu_api":
        base_ok = (
            a_end_omni == expected
            and any(c.ok and c.name == "A-end /health/live" for c in report.checks)
            and any(
                c.ok and c.name.startswith("gpu_health [expected]")
                for c in report.checks
            )
        )
        if not include_parse:
            return base_ok
        parse_ok = any(c.ok and c.name.startswith("parse_probe") for c in report.checks)
        return base_ok and parse_ok
    optional_prefixes = ("port :8002",)
    for check in report.checks:
        if any(check.name.startswith(p) for p in optional_prefixes):
            continue
        if not check.ok:
            return False
    return True


def format_report_human(report: ChainDiagnosticReport) -> str:
    lines = [
        "=== HAJIMI 链路诊断 ===",
        f"时间: {report.timestamp}",
        f"部署模式: {report.deployment_mode}",
        f"期望 OmniParser: {report.expected_omni_url}",
        "",
        "--- 配置 ---",
        f"  user_settings.omniparser.url = {report.config.get('user_settings', {}).get('omniparser_url')}",
        f"  server/.env OMNIPARSER_URL   = {report.config.get('server_env', {}).get('OMNIPARSER_URL')}",
        f"  server/.env LLM_SPEED_MODE   = {report.config.get('server_env', {}).get('LLM_SPEED_MODE', 'fast')}",
        f"  A 端 health.omniparser_url   = {report.url_consistency.get('a_end_health')}",
        f"  settings vs A 端一致         = {report.url_consistency.get('match_settings_vs_a_end')}",
        f"  settings vs .env 一致        = {report.url_consistency.get('match_settings_vs_env')}",
        "",
        "--- 探测 ---",
    ]
    for check in report.checks:
        tag = "PASS" if check.ok else "FAIL"
        ms = f" ({check.latency_ms}ms)" if check.latency_ms is not None else ""
        lines.append(f"[{tag}] {check.name}{ms}: {check.detail}")

    if report.issues:
        lines.extend(["", "--- 问题 ---"])
        for issue in report.issues:
            lines.append(f"  ! {issue}")

    if report.recommendations:
        lines.extend(["", "--- 建议 ---"])
        for rec in report.recommendations:
            lines.append(f"  → {rec}")

    if report.latency_summary:
        s = report.latency_summary
        lines.extend([
            "",
            "--- 延迟汇总 (ms) ---",
            f"  8010 live={s.get('a_end_live_ms')} health={s.get('a_end_health_ms')}",
            f"  9800 health={s.get('gpu_health_ms')} parse_probe={s.get('parse_ms')}",
            f"  llm_probe={s.get('llm_probe_ms')} e2e_inspect={s.get('e2e_inspect_ms')}",
            f"  e2e_process={s.get('e2e_process_ms')} "
            f"parse={s.get('e2e_process_parse_ms')} llm={s.get('e2e_process_llm_ms')}",
            f"  llm_reached={s.get('llm_reached')} "
            f"speed_mode={s.get('llm_speed_mode')} vision={s.get('llm_used_vision')}",
            f"  parse_probe={s.get('parse_probe_ms')} "
            f"parse_real_screen={s.get('parse_real_screen_ms')}",
        ])

    if report.billing_note:
        lines.extend(["", "--- OpenAI 计费 ---", f"  {report.billing_note}"])

    lines.extend([
        "",
        f"总体: {'就绪' if report.overall_ok else '未就绪'}",
    ])
    return "\n".join(lines)
