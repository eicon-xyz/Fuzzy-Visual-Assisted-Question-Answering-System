import json
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


def check_health() -> bool:
    """探测 A 端 /api/demo/health 是否可用。"""
    data = _fetch_health()
    return bool(data and data.get("status") == "ok")


def fetch_health() -> Optional[dict]:
    """获取 A 端 /api/demo/health 完整 JSON，不可用时返回 None。"""
    return _fetch_health()


def _check_detector_preflight() -> tuple[bool, str]:
    """检验 / 任务处理前共用的 A 端 + OmniParser 预检。"""
    if USE_MOCK_ONLY:
        return False, "需要 A 端真实检测，请关闭 HAJIMI_MOCK_ONLY"

    health = _fetch_health()
    if not health or health.get("status") != "ok":
        if DEPLOYMENT_MODE == "intranet":
            return (
                False,
                f"内网 A 端不可达 ({_api_base_url()})。请确认校园网/VPN 与地址是否正确。",
            )
        return False, f"A 端未启动。请点击设置「启动 OmniParser + A 端」或运行: {START_ALL_HINT}"

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


def check_inspect_preflight() -> tuple[bool, str]:
    """
    检验模式启动前预检。返回 (ok, message)；ok 为 False 时 message 为中文原因。
    在启动 InspectWorkerThread 之前调用，避免无意义的全屏截图与 CPU 峰值。
    """
    ok, msg = _check_detector_preflight()
    if not ok and "HAJIMI_MOCK_ONLY" in msg:
        return False, "检验模式需要 A 端 /inspect，请关闭 HAJIMI_MOCK_ONLY"
    return ok, msg


def check_process_preflight() -> tuple[bool, str]:
    """任务处理（/process）前预检，避免截图后才发现后端未就绪。"""
    return _check_detector_preflight()


def _format_connection_label(health: dict) -> str:
    base = _api_base_url()
    device = health.get("detector_device")
    if DEPLOYMENT_MODE == "intranet":
        if device == "cuda":
            return f"A 端已连接 (校园 GPU/cuda) {base}"
        return f"A 端已连接 (内网) {base}"
    if device == "cuda":
        return f"A 端已连接 (GPU/cuda) {base}"
    if device == "cpu":
        return f"A 端已连接 (本地 CPU，约 2–4 分钟/帧) {base}"
    if health.get("detector_active") == "replicate_omniparser":
        return f"A 端已连接 (云端 Replicate) {base}"
    return f"A 端已连接 ({base})"


def get_api_status_message() -> tuple[str, str]:
    """返回 (消息文本, 类型) 供 UI 展示。"""
    if USE_MOCK_ONLY:
        return "当前为纯 Mock 模式（HAJIMI_MOCK_ONLY=1）", "system"
    health = _fetch_health()
    if health and health.get("status") == "ok":
        msg = _format_connection_label(health)
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
            "或在系统设置切换为「本地启动」。",
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



def _request_json(
    path: str,
    payload: Optional[dict] = None,
    *,
    method: str = "POST",
    timeout: Optional[int] = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "X-Demo-Key": _demo_key()}
    req = urllib.request.Request(
        f"{_api_base_url()}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or _api_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ApiError("X-Demo-Key 不匹配，请检查 HAJIMI_DEMO_KEY") from exc
        raise ApiError(f"A 端 HTTP {exc.code}: {_read_http_error(exc)}") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        if _is_timeout_error(exc):
            raise ApiError(f"A 端请求超时（{timeout or _api_timeout()}s）") from exc
        raise ApiError(
            f"A 端不可达 ({getattr(exc, 'reason', exc)})。请先运行: {SERVER_START_HINT}"
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
) -> dict:
    if USE_MOCK_ONLY:
        return _fallback_process(query, screen_width, screen_height)

    if not check_health():
        if ALLOW_MOCK_FALLBACK:
            print("[API] A 端不可用，回退 Mock（HAJIMI_MOCK_FALLBACK=1）")
            return _fallback_process(query, screen_width, screen_height)
        raise ApiError(f"A 端未启动。请先运行: {SERVER_START_HINT}")

    ok, reason = check_process_preflight()
    if not ok:
        raise ApiError(reason)

    data = _request_json(
        "/api/demo/process",
        {
            "query": query,
            "image": image_data_uri,
            "window_title": window_title,
            "context": [],
        },
        timeout=PROCESS_TIMEOUT,
    )

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
) -> dict:
    ok, reason = check_process_preflight()
    if not ok:
        raise ApiError(reason)

    data = _request_json(
        "/api/demo/relocate",
        {
            "task_id": task_id,
            "step_index": step_index,
            "image": image_data_uri,
        },
        timeout=PROCESS_TIMEOUT,
    )
    if data.get("success") is False:
        raise ApiError("重新定位失败：success=false")
    data["_source"] = "server"
    ref = data.get("reference_resolution")
    if ref and len(ref) >= 2:
        data["_ref_size"] = [int(ref[0]), int(ref[1])]
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
) -> dict:
    if USE_MOCK_ONLY:
        return mock_advance_step(task_id, step_index, fingerprint, action, steps)

    try:
        return _request_json(
            "/api/demo/step",
            {
                "task_id": task_id,
                "action": action,
                "step_index": step_index,
                "fingerprint": fingerprint or "",
            },
        )
    except ApiError as exc:
        if ALLOW_MOCK_FALLBACK:
            print(f"[API] step 失败，回退 Mock: {exc}")
            return mock_advance_step(task_id, step_index, fingerprint, action, steps)
        raise
