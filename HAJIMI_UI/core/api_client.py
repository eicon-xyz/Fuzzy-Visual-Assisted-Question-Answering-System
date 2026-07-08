import json
import os
import socket
import urllib.error
import urllib.request
from typing import List, Optional

import config
from config import (
    ALLOW_MOCK_FALLBACK,
    DEPLOYMENT_MODE,
    HEALTH_TIMEOUT,
    INSPECT_TIMEOUT,
    L4_START_HINT,
    L5_START_HINT,
    PROCESS_TIMEOUT,
    SERVER_START_HINT,
    START_ALL_HINT,
    USE_MOCK_ONLY,
)
from core.mock_backend import advance_step as mock_advance_step
from core.mock_backend import process_query, register_task


class ApiError(Exception):
    """A 端 API 调用失败（连接、认证或业务错误）"""


def reload_client_config() -> None:
    """user_settings.apply 后刷新本模块对 config 的引用。"""
    config.reload_from_env()


def _api_base_url() -> str:
    return config.API_BASE_URL


def _l5_api_base_url() -> str:
    return config.L5_API_URL


def _demo_key() -> str:
    return config.DEMO_KEY


def _api_timeout() -> int:
    return config.API_TIMEOUT


def _fetch_health() -> Optional[dict]:
    req = urllib.request.Request(
        f"{_api_base_url()}/api/demo/health",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _fetch_health_live() -> Optional[dict]:
    """轻量存活探测，不依赖 OmniParser。"""
    req = urllib.request.Request(
        f"{_api_base_url()}/api/demo/health/live",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def check_health() -> bool:
    """探测 A 端是否可用；L4 路径优先 /health/live（不依赖 OmniParser）。"""
    live = _fetch_health_live()
    if live and live.get("status") == "ok":
        return True
    data = _fetch_health()
    return bool(data and data.get("status") == "ok")


def _fetch_l5_health_live() -> Optional[dict]:
    """L5 Sidecar (:8011) 轻量存活探测；无 /health/live 时回退 /health。"""
    base = _l5_api_base_url().rstrip("/")
    for path in ("/api/demo/health/live", "/api/demo/health"):
        req = urllib.request.Request(f"{base}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                if resp.status not in (200, 503):
                    continue
                data = json.loads(resp.read().decode("utf-8"))
                if path.endswith("/health") and resp.status == 503:
                    return {"status": "ok", "degraded": True, **data}
                return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            if exc.code == 503:
                try:
                    data = json.loads(exc.read().decode("utf-8"))
                except Exception:
                    data = {}
                return {"status": "ok", "degraded": True, **data}
        except Exception:
            continue
    return None


def check_l5_health() -> bool:
    """探测 L5 Sidecar (new_JIMI :8011) 是否可用。"""
    live = _fetch_l5_health_live()
    return bool(live and live.get("status") in ("ok", "degraded"))


def fetch_l5_health() -> Optional[dict]:
    """GET L5 Sidecar /api/demo/health，不可用时返回 None。"""
    req = urllib.request.Request(
        f"{_l5_api_base_url().rstrip('/')}/api/demo/health",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def fetch_health() -> Optional[dict]:
    """获取 A 端 /api/demo/health 完整 JSON，不可用时返回 None。"""
    return _fetch_health()


def _probe_omni_api(base_url: str, timeout: float = 5.0) -> Optional[dict]:
    """Probe OmniParser GPU API /health (e.g. tunnel :9800)."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return None
    req = urllib.request.Request(f"{base}/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _expected_omni_url() -> str:
    try:
        from core.defaults import DEFAULT_OMNI_GPU_API_URL, DEFAULT_OMNI_LOCAL_URL
        from core.user_settings import load_user_settings

        data = load_user_settings()
        mode = data.get("deployment_mode", "gpu_api")
        omni = data.get("omniparser") or {}
        if omni.get("url"):
            return _normalize_url(str(omni["url"]))
        if mode == "gpu_api":
            return _normalize_url(DEFAULT_OMNI_GPU_API_URL)
        return _normalize_url(DEFAULT_OMNI_LOCAL_URL)
    except Exception:
        return "http://127.0.0.1:9800"


def _a_end_unreachable_message() -> str:
    if DEPLOYMENT_MODE == "intranet":
        return (
            f"内网 A 端不可达 ({_api_base_url()})。请确认校园网/VPN 与地址是否正确。"
        )
    if not _routing_needs_omniparser():
        return (
            f"A 端未启动（L4 Vision 仅需本机 A 端 + LLM，无需 OmniParser）。"
            f"请设置页点击「启动 A 端」或运行: {L4_START_HINT}"
        )
    if DEPLOYMENT_MODE == "gpu_api":
        return (
            "A 端未启动。请点击设置「启动 A 端」或运行根目录 启动HAJIMI.bat"
        )
    return f"A 端未启动。请点击设置「启动 A 端」或运行: {SERVER_START_HINT}"


def _read_server_env_value(key: str) -> str:
    from core.routing_config import _read_env_file

    return (os.environ.get(key) or _read_env_file(key) or "").strip()


def _check_a_end_preflight() -> tuple[bool, str]:
    """仅确认 A 端 FastAPI 可用（/health/live 或 /health）。"""
    if USE_MOCK_ONLY:
        return False, "需要 A 端真实检测，请关闭 HAJIMI_MOCK_ONLY"

    live = _fetch_health_live()
    if live and live.get("status") == "ok":
        return True, ""

    health = _fetch_health()
    if health and health.get("status") == "ok":
        return True, ""

    return False, _a_end_unreachable_message()


def _check_llm_preflight() -> tuple[bool, str]:
    """L4 / L3_DEFERRED 路径：确认 LLM API 已配置。"""
    health = _fetch_health()
    if health:
        if health.get("l4_capable") is True:
            return True, ""
        if health.get("llm_configured") is False:
            return False, (
                "L4 需要 LLM：请在 server/.env 配置 LLM_API_KEY + LLM_BASE_URL，"
                "或 DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL"
            )

    api_key = _read_server_env_value("LLM_API_KEY") or _read_server_env_value(
        "DEEPSEEK_API_KEY"
    )
    base_url = _read_server_env_value("LLM_BASE_URL") or _read_server_env_value(
        "DEEPSEEK_BASE_URL"
    )
    if not api_key:
        return False, (
            "L4 需要 LLM：请在 server/.env 配置 LLM_API_KEY 或 DEEPSEEK_API_KEY"
        )
    if not base_url:
        return False, (
            "L4 需要 LLM：请在 server/.env 配置 LLM_BASE_URL 或 DEEPSEEK_BASE_URL"
        )
    return True, ""


def _check_omniparser_preflight(health: dict) -> tuple[bool, str]:
    """OmniParser 完整预检（inspect / precision 模式）。"""
    if DEPLOYMENT_MODE == "gpu_api":
        expected = _expected_omni_url()
        a_end_url = _normalize_url(health.get("omniparser_url") or "")
        if a_end_url and a_end_url != expected:
            return (
                False,
                f"A 端 OmniParser 地址为 {a_end_url}，与设置 {expected} 不一致。"
                "请保存设置并点击「启动 A 端」重启 A 端（或运行 scripts\\start_server.bat）。",
            )
        if ":8002" in a_end_url:
            return (
                False,
                f"A 端仍指向本地 CPU ({a_end_url})，GPU API 模式需要 {expected}。"
                "请确认 server/.env 中 OMNIPARSER_URL 并重启 A 端。",
            )
        omni_url = a_end_url or expected
        gpu = _probe_omni_api(omni_url)
        if not gpu:
            return (
                False,
                f"GPU OmniParser 隧道未就绪 ({omni_url})。"
                "inspect 需走 GPU API（约 2–5 秒），不是本地 CPU 2–4 分钟。"
                "请运行设置页「一键 GPU」或根目录 启动HAJIMI.bat",
            )
        if not gpu.get("ready"):
            return False, "GPU OmniParser 模型仍在加载，请稍候再试。"
        device = (gpu.get("device") or health.get("detector_device") or "").lower()
        if device == "cpu":
            return (
                False,
                f"OmniParser 报告 device=cpu（{omni_url}），GPU API 模式需要 cuda。"
                "请关闭本地 :8002 OmniParser，并确认 SSH 隧道指向远程 GPU。",
            )
        ready = health.get("omniparser_ready")
        if ready is False:
            return (
                False,
                "A 端报告 OmniParser 未就绪。请确认 server/.env 中 OMNIPARSER_URL=:9800 并已重启 A 端。",
            )
        return True, ""

    if DEPLOYMENT_MODE == "intranet":
        ready = health.get("omniparser_ready")
        if ready is False:
            return False, "远程 A 端报告 OmniParser 未就绪，请联系 A 端同学重启检测服务。"
        return True, ""

    backend = health.get("detector_backend")
    if backend is None:
        if health.get("omniparser_ready") is not False:
            return True, ""
        return (
            False,
            "A 端未报告 detector_backend（端口上可能是旧版或多开实例）。"
            f"请先运行 scripts\\stop_all.bat，再 {START_ALL_HINT}",
        )
    if backend in ("local_omniparser", "auto"):
        ready = health.get("omniparser_ready")
        if ready is False:
            return (
                False,
                "OmniParser 未就绪。请先运行 scripts\\start_omniparser.bat，"
                "或设置页「启动 OmniParser + A 端」，等待「Omniparser initialized」。",
            )
        if ready is None and backend == "local_omniparser":
            return (
                False,
                "A 端未报告 OmniParser 状态（可能是旧版 A 端）。"
                f"请 scripts\\stop_all.bat 后 {START_ALL_HINT}",
            )
    return True, ""


def _check_detector_preflight(*, require_omniparser: bool = True) -> tuple[bool, str]:
    """A 端预检；require_omniparser=True 时追加 OmniParser 探测。"""
    ok, msg = _check_a_end_preflight()
    if not ok:
        return ok, msg

    if not require_omniparser:
        return _check_llm_preflight()

    health = _fetch_health() or {}
    return _check_omniparser_preflight(health)


def _routing_needs_omniparser() -> bool:
    from core.routing_config import routing_needs_omniparser

    return routing_needs_omniparser()


def check_inspect_preflight() -> tuple[bool, str]:
    """
    检验模式启动前预检。返回 (ok, message)；ok 为 False 时 message 为中文原因。
    在启动 InspectWorkerThread 之前调用，避免无意义的全屏截图与 CPU 峰值。
    """
    ok, msg = _check_detector_preflight(require_omniparser=True)
    if not ok and "HAJIMI_MOCK_ONLY" in msg:
        return False, "检验模式需要 A 端 /inspect，请关闭 HAJIMI_MOCK_ONLY"
    return ok, msg


def check_process_preflight() -> tuple[bool, str]:
    """任务处理前预检：L4/L3_DEFERRED 仅 A 端+LLM；precision 需 OmniParser。"""
    if _routing_needs_omniparser():
        return _check_detector_preflight(require_omniparser=True)
    ok, msg = _check_a_end_preflight()
    if not ok:
        return ok, msg
    return _check_llm_preflight()


def _ensure_process_ready() -> tuple[bool, str]:
    """L4 等轻量路径：预检失败时尝试自动启动本机 A 端并重试一次。"""
    ok, msg = check_process_preflight()
    if ok:
        return True, ""

    if _routing_needs_omniparser():
        return False, msg

    a_ok, a_msg = _check_a_end_preflight()
    if a_ok:
        return False, msg

    try:
        from core.service_manager import ensure_a_end_running

        if ensure_a_end_running():
            return check_process_preflight()
    except Exception:
        pass
    return False, a_msg


def _format_connection_label(health: dict) -> str:
    base = _api_base_url()
    device = health.get("detector_device")
    if DEPLOYMENT_MODE == "intranet":
        if device == "cuda":
            return f"A 端已连接 (校园 GPU/cuda) {base}"
        return f"A 端已连接 (内网) {base}"
    if DEPLOYMENT_MODE == "gpu_api":
        omni = health.get("omniparser_url") or "http://127.0.0.1:9800"
        if device == "cuda":
            return f"A 端已连接 (GPU API/cuda, {omni}) {base}"
        return f"A 端已连接 (GPU API, {omni}) {base}"
    if device == "cuda":
        return f"A 端已连接 (GPU/cuda) {base}"
    if device == "cpu":
        return f"A 端已连接 (本地 CPU，约 2–4 分钟/帧) {base}"
    if health.get("detector_active") == "replicate_omniparser":
        return f"A 端已连接 (云端 Replicate) {base}"
    return f"A 端已连接 ({base})"


def get_api_status_message() -> tuple[str, str]:
    """返回 (消息文本, 类型) 供 UI 展示。"""
    from core.routing_config import get_routing_mode, routing_needs_omniparser

    if USE_MOCK_ONLY:
        return "当前为纯 Mock 模式（HAJIMI_MOCK_ONLY=1）", "system"

    l4_route = not routing_needs_omniparser()
    live = _fetch_health_live()
    health = _fetch_health()

    if l4_route and live and live.get("status") == "ok":
        routing = get_routing_mode()
        base = _api_base_url()
        if health and health.get("l4_capable"):
            return f"A 端已连接 (L4 Vision, routing={routing}) {base}", "system"
        if health and health.get("llm_configured") is False:
            return (
                f"A 端已连接，但 LLM 未配置 — 请在设置填写 API Key（L4 需要 Vision 模型） {base}",
                "system danger",
            )
        return f"A 端已连接 (L4 Vision, routing={routing}) {base}", "system"

    if health and health.get("status") == "ok":
        msg = _format_connection_label(health)
        if DEPLOYMENT_MODE == "gpu_api":
            omni_url = health.get("omniparser_url") or "http://127.0.0.1:9800"
            gpu = _probe_omni_api(omni_url, timeout=3.0)
            if not gpu or not gpu.get("ready"):
                return (
                    f"{msg}，但 :9800 隧道未就绪 — 请设置页「一键 GPU」"
                    "或根目录 启动HAJIMI.bat",
                    "system danger",
                )
            if health.get("omniparser_ready") is False:
                return (
                    f"{msg}，但 A 端 OmniParser 未就绪 — 请保存设置并重启 A 端",
                    "system danger",
                )
            return msg, "system"
        if DEPLOYMENT_MODE != "intranet":
            backend = health.get("detector_backend")
            if backend in ("local_omniparser", "auto"):
                if health.get("omniparser_ready") is False:
                    return (
                        f"{msg}，但 OmniParser 未就绪 — 请设置页「启动 OmniParser + A 端」"
                        f"或 {START_ALL_HINT}",
                        "system danger",
                    )
            if backend is None:
                if health.get("omniparser_ready") is not False:
                    return msg, "system"
                return (
                    f"{msg}，但缺少 detector_backend（可能旧版 A 端或多开）。"
                    f"请 scripts\\stop_all.bat 后 {START_ALL_HINT}",
                    "system danger",
                )
        return msg, "system"
    if DEPLOYMENT_MODE == "intranet":
        return (
            f"内网 A 端不可达 ({_api_base_url()})。请检查校园网/VPN 与 SSH 隧道，"
            "或在系统设置切换为「GPU API」。",
            "system",
        )
    if l4_route:
        return (
            f"A 端未连接（L4 仅需本机 :{config.SERVER_DEFAULT_PORT} + LLM）。"
            f"请设置页「启动 A 端」或 {L4_START_HINT}",
            "system",
        )
    if DEPLOYMENT_MODE == "gpu_api":
        return (
            f"A 端未连接。请运行根目录 启动HAJIMI.bat 或设置页「启动 A 端」。"
            " UI 将每 10s 自动重试连接。",
            "system",
        )
    if ALLOW_MOCK_FALLBACK:
        return (
            f"UI 已就绪；A 端未连接，将回退本地 Mock。启动: {SERVER_START_HINT}",
            "system",
        )
    return (
        f"UI 已就绪；A 端未连接（可选联调: {SERVER_START_HINT}）。"
        " 仅看界面可设置 HAJIMI_MOCK_ONLY=1",
        "system",
    )


def get_api_status_with_connection() -> tuple[str, str, bool]:
    """返回 (消息, 类型, 是否视为已连接) 供后台轮询使用。"""
    text, msg_type = get_api_status_message()
    connected = (
        "danger" not in msg_type
        and "已连接" in text
        and "未连接" not in text
        and "不可达" not in text
    )
    return text, msg_type, connected


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return True
        if "timed out" in str(reason).lower():
            return True
    return False


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        err = body.get("error") or body.get("detail")
        if isinstance(err, dict):
            return err.get("message") or str(err)
        if isinstance(err, str):
            return err
    except Exception:
        pass
    return str(exc)


def _format_inspect_error_message(msg: str, timeout: int) -> str:
    if "超时" in msg or "timed out" in msg.lower():
        if DEPLOYMENT_MODE == "gpu_api":
            return (
                f"检测请求超时（已等待 {timeout}s）。多数卡在 OmniParser 全屏 parse，"
                "与 OpenAI 无关。请查看 A 端 [OmniParser Client] 日志，"
                "或运行设置页「链路诊断」/ python scripts/diagnose_inspect.py --full。"
            )
        return (
            f"检测请求超时（已等待 {timeout}s）。CPU 模式下全屏检测通常需 2–4 分钟。"
            "请勿重复点击；若刚超时，OmniParser 可能仍在后台解析，请等待 2 分钟后再试一次。"
        )
    if "502" in msg:
        if "not reachable" in msg.lower():
            return (
                "OmniParser 未启动或不可达。"
                "请先运行 scripts\\start_omniparser.bat，等待「Omniparser initialized」后再检测。"
            )
        if "HTTP 500" in msg or "Internal Server Error" in msg:
            return (
                "OmniParser 内部错误（可能为空白屏无 UI 元素、内存不足或上一次解析尚未结束）。"
                "RTX 50 系若误启 cuda 也会 500，请 scripts\\stop_all.bat 后重跑 "
                "scripts\\start_omniparser.bat（应显示 cpu mode），"
                "单独再试一次并等待 2–4 分钟。"
            )
        if "DETECTOR_FAILED" in msg or "OmniParser" in msg or "local OmniParser" in msg:
            return f"UI 检测器失败: {msg.split(': ', 1)[-1]}"
    if "422" in msg and "NO_ELEMENTS" in msg.upper():
        return "未检测到 UI 元素，请换一张包含可见控件的截图再试。"
    return msg


def _format_process_error_message(msg: str, timeout: int) -> str:
    lower = msg.lower()
    if "chat/completions" in lower and "404" in msg:
        return (
            "LLM API 路径错误：当前中转站（如 daseinai）需使用 Responses API。"
            "请在 server/.env 设置 LLM_WIRE_API=responses，"
            "Base URL 保持 https://www.daseinai.xyz/v1，保存后重启 A 端。"
            f" 原始错误: {msg}"
        )
    if "404 not found" in lower and ("daseinai" in lower or "responses" in lower):
        return (
            "LLM 模型或 API 地址不可用。请确认："
            "1) LLM_WIRE_API=responses；2) 模型名 gpt-5.5 在中转站可用；"
            "3) 重启 A 端使 .env 生效。"
            f" 详情: {msg}"
        )
    if "500" in msg and ("llm" in lower or "chat/completions" in lower or "/responses" in lower):
        return f"LLM 调用失败（A 端已连接，问题在 API 配置或模型名）: {msg}"
    if "超时" in msg or "timed out" in lower:
        if DEPLOYMENT_MODE == "gpu_api":
            return (
                f"处理请求超时（已等待 {timeout}s）。"
                "可能卡在 OmniParser parse 或 LLM 阶段；"
                "若 A 端控制台无 [LLM] 日志，多半仍在 parse。"
                "运行 python scripts/diagnose_inspect.py --llm / --process 排查。"
            )
        return (
            f"处理请求超时（已等待 {timeout}s）。"
            "CPU 模式下 parse 可能需数分钟；请勿重复提交。"
        )
    return msg


def _request_json(
    path: str,
    payload: Optional[dict] = None,
    *,
    method: str = "POST",
    timeout: Optional[int] = None,
    base_url: Optional[str] = None,
) -> dict:
    root = (base_url or _api_base_url()).rstrip("/")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "X-Demo-Key": _demo_key()}
    req = urllib.request.Request(
        f"{root}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    is_l5 = root.rstrip("/") == _l5_api_base_url().rstrip("/")
    start_hint = L5_START_HINT if is_l5 else SERVER_START_HINT
    label = "L5 Sidecar" if is_l5 else "A 端"
    try:
        with urllib.request.urlopen(req, timeout=timeout or _api_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ApiError("X-Demo-Key 不匹配，请检查 HAJIMI_DEMO_KEY") from exc
        raise ApiError(f"{label} HTTP {exc.code}: {_read_http_error(exc)}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if _is_timeout_error(exc):
            raise ApiError(f"{label} 请求超时（{timeout or _api_timeout()}s）") from exc
        raise ApiError(
            f"{label} 不可达 ({getattr(exc, 'reason', exc)})。请先运行: {start_hint}"
        ) from exc


def _fallback_process(query: str, screen_width: int, screen_height: int) -> dict:
    mock = process_query(query, screen_width, screen_height)
    if mock:
        return mock
    raise ApiError("Mock 未匹配到该问题，请尝试输入「怎么安装微信」")


def process(
    query: str,
    image_data_uri: str,
    window_title: str = "桌面",
    screen_width: int = 1920,
    screen_height: int = 1080,
    screen_fingerprint: Optional[str] = None,
    *,
    capture_size: Optional[list] = None,
    upload_size: Optional[list] = None,
    screen_metrics: Optional[dict] = None,
    assist_bundle: Optional[dict] = None,
) -> dict:
    if USE_MOCK_ONLY:
        return _fallback_process(query, screen_width, screen_height)

    ok, reason = _ensure_process_ready()
    if not ok:
        if ALLOW_MOCK_FALLBACK:
            print("[API] A 端不可用，回退 Mock（HAJIMI_MOCK_FALLBACK=1）")
            return _fallback_process(query, screen_width, screen_height)
        raise ApiError(reason)

    try:
        payload = {
            "query": query,
            "image": image_data_uri,
            "window_title": window_title,
            "context": [],
        }
        if screen_fingerprint:
            payload["screen_fingerprint"] = screen_fingerprint
        if capture_size:
            payload["capture_size"] = capture_size
        if upload_size:
            payload["upload_size"] = upload_size
        if screen_metrics:
            payload["screen_metrics"] = screen_metrics
        if assist_bundle:
            payload["assist_bundle"] = assist_bundle
        data = _request_json(
            "/api/demo/process",
            payload,
            timeout=PROCESS_TIMEOUT,
        )
    except ApiError as exc:
        raise ApiError(
            _format_process_error_message(str(exc), PROCESS_TIMEOUT)
        ) from exc

    if not data.get("success"):
        redline = data.get("redline")
        if isinstance(redline, dict) and redline.get("triggered"):
            raise ApiError(redline.get("message") or "请求触发安全红线，无法执行")
        raise ApiError("A 端处理失败：success=false")

    steps = data.get("steps") or []
    if not data.get("task_id") or not steps:
        raise ApiError("A 端未返回有效 task_id 或 steps")

    if ALLOW_MOCK_FALLBACK:
        register_task(data["task_id"], steps)

    data["_source"] = "server"
    ref = data.get("reference_resolution")
    if ref and len(ref) >= 2:
        data["_ref_size"] = [int(ref[0]), int(ref[1])]
    return data


def relocate_step(
    task_id: str,
    step_index: int,
    image_data_uri: str,
    screen_width: int = 1920,
    screen_height: int = 1080,
    *,
    capture_size: Optional[list] = None,
    upload_size: Optional[list] = None,
    screen_metrics: Optional[dict] = None,
    assist_bundle: Optional[dict] = None,
) -> dict:
    ok, reason = check_process_preflight()
    if not ok:
        raise ApiError(reason)

    try:
        data = _request_json(
            "/api/demo/relocate",
            {
                "task_id": task_id,
                "step_index": step_index,
                "image": image_data_uri,
                **(
                    {"capture_size": capture_size}
                    if capture_size
                    else {}
                ),
                **(
                    {"upload_size": upload_size}
                    if upload_size
                    else {}
                ),
                **(
                    {"screen_metrics": screen_metrics}
                    if screen_metrics
                    else {}
                ),
                **(
                    {"assist_bundle": assist_bundle}
                    if assist_bundle
                    else {}
                ),
            },
            timeout=PROCESS_TIMEOUT,
        )
    except ApiError as exc:
        raise ApiError(
            _format_process_error_message(str(exc), PROCESS_TIMEOUT)
        ) from exc
    if data.get("success") is False:
        raise ApiError("重新定位失败：success=false")
    data["_source"] = "server"
    ref = data.get("reference_resolution")
    if ref and len(ref) >= 2:
        data["_ref_size"] = [int(ref[0]), int(ref[1])]
    return data


def locate_step(
    task_id: str,
    step_index: int,
    image_data_uri: str,
    query: Optional[str] = None,
    *,
    capture_size: Optional[list] = None,
    upload_size: Optional[list] = None,
    screen_metrics: Optional[dict] = None,
) -> dict:
    ok, reason = check_process_preflight()
    if not ok:
        raise ApiError(reason)
    payload = {
        "task_id": task_id,
        "step_index": step_index,
        "image": image_data_uri,
    }
    if query:
        payload["query"] = query
    if capture_size:
        payload["capture_size"] = capture_size
    if upload_size:
        payload["upload_size"] = upload_size
    if screen_metrics:
        payload["screen_metrics"] = screen_metrics
    try:
        data = _request_json("/api/demo/locate", payload, timeout=PROCESS_TIMEOUT)
    except ApiError as exc:
        raise ApiError(
            _format_process_error_message(str(exc), PROCESS_TIMEOUT)
        ) from exc
    data["_source"] = "server"
    return data


def inspect(
    image_data_uri: str,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    if USE_MOCK_ONLY:
        raise ApiError("检验模式需要 A 端 /inspect，请关闭 HAJIMI_MOCK_ONLY")

    if not check_health():
        raise ApiError(f"A 端未启动。请先运行: {SERVER_START_HINT}")

    health = _fetch_health()
    if (
        health
        and health.get("detector_backend") in ("local_omniparser", "auto")
        and health.get("omniparser_ready") is False
        and DEPLOYMENT_MODE != "intranet"
    ):
        raise ApiError(
            "OmniParser 未就绪。请先运行 scripts\\start_omniparser.bat，"
            "等待终端出现「Omniparser initialized」后再检测。"
        )

    try:
        data = _request_json(
            "/api/demo/inspect",
            {
                "image": image_data_uri,
                "screen_width": screen_width,
                "screen_height": screen_height,
            },
            timeout=INSPECT_TIMEOUT,
        )
    except ApiError as exc:
        raise ApiError(
            _format_inspect_error_message(str(exc), INSPECT_TIMEOUT)
        ) from exc

    if data.get("success") is False:
        raise ApiError("A 端 inspect 失败：success=false")

    data["_source"] = "server"
    return data


def advance_step(
    task_id: str,
    step_index: int,
    fingerprint: str = "",
    action: str = "advance",
    steps: Optional[List[dict]] = None,
    image_data_uri: Optional[str] = None,
    *,
    capture_size: Optional[list] = None,
    upload_size: Optional[list] = None,
    screen_metrics: Optional[dict] = None,
    assist_bundle: Optional[dict] = None,
) -> dict:
    if USE_MOCK_ONLY:
        return mock_advance_step(task_id, step_index, fingerprint, action, steps)

    try:
        payload = {
            "task_id": task_id,
            "action": action,
            "step_index": step_index,
            "fingerprint": fingerprint or "",
        }
        if image_data_uri:
            payload["image"] = image_data_uri
        if capture_size:
            payload["capture_size"] = capture_size
        if upload_size:
            payload["upload_size"] = upload_size
        if screen_metrics:
            payload["screen_metrics"] = screen_metrics
        if assist_bundle:
            payload["assist_bundle"] = assist_bundle
        return _request_json("/api/demo/step", payload)
    except ApiError as exc:
        if ALLOW_MOCK_FALLBACK:
            print(f"[API] step 失败，回退 Mock: {exc}")
            return mock_advance_step(task_id, step_index, fingerprint, action, steps)
        raise


def _ensure_l5_ready() -> tuple[bool, str]:
    """L5 路径：预检 8011 Sidecar，失败时尝试 auto-launch。"""
    if check_l5_health():
        return True, ""
    try:
        from core.l5_sidecar_launcher import ensure_l5_sidecar_running

        return ensure_l5_sidecar_running()
    except Exception as exc:
        return False, f"L5 Sidecar 不可用: {exc}"


def execute_task(
    query: str,
    image_data_uri: Optional[str] = None,
    *,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> dict:
    """L5：提交自动执行任务到 new_JIMI Sidecar (:8011)，返回 plan + task_id。"""
    if USE_MOCK_ONLY:
        raise ApiError("Mock 模式不支持 L5 自动执行")

    ok, reason = _ensure_l5_ready()
    if not ok:
        raise ApiError(reason or f"L5 Sidecar 未就绪，请先运行: {L5_START_HINT}")

    payload: dict = {
        "query": query,
        "image": image_data_uri,
        "context": [],
        "screen_width": screen_width,
        "screen_height": screen_height,
    }
    data = _request_json(
        "/api/demo/execute",
        payload,
        timeout=PROCESS_TIMEOUT,
        base_url=_l5_api_base_url(),
    )
    if not data.get("success"):
        err = data.get("error") or {}
        if isinstance(err, dict):
            raise ApiError(err.get("message") or "L5 执行提交失败")
        raise ApiError("L5 执行提交失败")
    if not data.get("task_id"):
        raise ApiError("L5 Sidecar 未返回 task_id")
    data["_source"] = "l5_sidecar"
    return data


def cancel_task(task_id: str) -> dict:
    """L5：取消进行中的自动执行任务（Sidecar :8011）。"""
    if USE_MOCK_ONLY:
        return {"success": False, "message": "Mock 模式无 L5 任务"}
    return _request_json(
        "/api/demo/cancel",
        {"task_id": task_id},
        timeout=min(_api_timeout(), 30),
        base_url=_l5_api_base_url(),
    )
