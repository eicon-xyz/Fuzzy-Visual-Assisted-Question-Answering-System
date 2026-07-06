#!/usr/bin/env python3
"""
test_parse_local.py — 本地 PC 端测试 (调用远程 GPU API via SSH 隧道)
前置: GPU 上 omniparser_api 已启动; 本地 ssh -L 9800:127.0.0.1:9800 ...
用法: scripts\\run_test_parse_local.bat  或  python test_parse_local.py [image.png]
"""
import sys
import os
import json
import base64
import time
import argparse
import urllib.request
import urllib.error
from pathlib import Path

API_URL = os.getenv("OMNIPARSER_URL", "http://127.0.0.1:9800")
HEALTH_TIMEOUT = int(os.getenv("OMNIPARSER_HEALTH_TIMEOUT", "5"))
PARSE_TIMEOUT = int(os.getenv("OMNIPARSER_TIMEOUT", "360"))


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def capture_screen_base64() -> str:
    try:
        import mss
        from PIL import Image
    except ImportError:
        print("截图需要: pip install pillow mss")
        print("或传图片: python test_parse_local.py image.png")
        sys.exit(1)

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def base64_to_file(b64: str, output_path: str):
    if "," in b64 and b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(b64))


def health_check(base_url: str) -> dict:
    url = f"{base_url.rstrip('/')}/health"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"无法连接 {base_url}\n"
            f"  原因: {e}\n"
            f"  请确认:\n"
            f"  1. scripts\\start_tunnel_9800.bat 已运行\n"
            f"  2. GPU 内: cd /workspace/code/omniparser_api && ./start.sh\n"
            f"  3. curl http://127.0.0.1:9800/health"
        ) from e
    except TimeoutError as e:
        raise ConnectionError(f"连接超时 ({HEALTH_TIMEOUT}s): {base_url}") from e


def call_parse(base_url: str, b64_image: str) -> dict:
    url = f"{base_url.rstrip('/')}/parse/"
    body = json.dumps({"base64_image": b64_image}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=PARSE_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        print(f"  HTTP {e.code}: {body_text}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  连接失败: {e}")
        sys.exit(1)
    except TimeoutError:
        print(f"  请求超时 ({PARSE_TIMEOUT}s)")
        sys.exit(1)

    elapsed = time.time() - t0
    server_latency = data.get("latency_ms", 0)
    print("  解析完成")
    print(f"  网络往返: {elapsed:.1f}s | 服务端推理: {server_latency}ms")
    return data


def print_elements(elements: list):
    if not elements:
        print("  (无元素)")
        return

    types_count = {}
    for e in elements:
        t = e.get("element_type", "other")
        types_count[t] = types_count.get(t, 0) + 1

    print(f"\n{'='*70}")
    print(f"  UI 元素 (共 {len(elements)} 个)")
    print(f"{'='*70}")
    print(f"  类型分布: {json.dumps(types_count, ensure_ascii=False)}")
    print()
    print(f"  {'ID':<8} {'类型':<14} {'文字/描述':<36} {'bbox'}")
    print(f"  {'-'*8} {'-'*14} {'-'*36} {'-'*24}")

    for elem in elements:
        eid = str(elem.get("element_id", "~?"))
        etype = elem.get("element_type") or "other"
        text = elem.get("text") or elem.get("content") or ""
        text = text[:34]
        bbox = elem.get("bbox", [])
        bbox_str = f"[{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}]" if len(bbox) == 4 else str(bbox)
        print(f"  {eid:<8} {etype:<14} {text:<36} {bbox_str}")


def main():
    parser = argparse.ArgumentParser(description="OmniParser GPU API 本地测试")
    parser.add_argument("image", nargs="?", help="截图路径 (不传则截屏)")
    parser.add_argument("--url", default=API_URL, help=f"API 地址 (默认: {API_URL})")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  OmniParser GPU API — 本地 PC 端测试")
    print("=" * 70)
    print(f"  GPU 服务器: {base_url}")

    print("\n[1/4] 检查 GPU 服务器连接...")
    try:
        health = health_check(base_url)
        print(f"  状态:     {health.get('status', '?')}")
        print(f"  就绪:     {health.get('ready', False)}")
        print(f"  GPU:      {health.get('gpu_name', 'N/A')}")
        print(f"  CUDA:     {health.get('cuda_available', False)}")
        if not health.get("ready"):
            print("  模型未就绪，请稍候再试")
            sys.exit(1)
    except ConnectionError as e:
        print(f"  {e}")
        sys.exit(1)

    print("\n[2/4] 准备图片...")
    if args.image:
        if not os.path.exists(args.image):
            print(f"  图片不存在: {args.image}")
            sys.exit(1)
        print(f"  读取: {args.image}")
        b64 = image_to_base64(args.image)
    else:
        print("  截取当前屏幕...")
        b64 = capture_screen_base64()
    print(f"  Base64 大小: {len(b64)/1024:.0f} KB")

    print(f"\n[3/4] 调用 GPU API ({base_url}/parse/) ...")
    result = call_parse(base_url, b64)

    print("\n[4/4] 处理结果...")
    elements = result.get("parsed_content_list") or result.get("elements") or []
    som_b64 = result.get("som_image_base64") or result.get("annotated_image")
    print(f"  检测元素: {len(elements)} 个")
    print(f"  设备:     {result.get('device', 'unknown')}")
    print_elements(elements)

    if som_b64:
        som_path = out_dir / "output_som_local.png"
        base64_to_file(som_b64, str(som_path))
        print(f"\n  SoM 标注图: {som_path}")

    json_path = out_dir / "output_elements_local.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"gpu_server": base_url, "result": result}, f, ensure_ascii=False, indent=2)
    print(f"  完整结果: {json_path}")
    print("\n  测试完成")


if __name__ == "__main__":
    main()
