"""在浏览器中打开 index.html 做算法演示（full 模式）。"""
import http.server
import os
import socket
import sys
import threading
import webbrowser


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    os.chdir(web_dir)
    port = _find_free_port()

    handler = http.server.SimpleHTTPRequestHandler
    httpd = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/index.html"
    print(f"[HAJIMI] 浏览器 Demo 已启动: {url}")
    print("  此为 HTML 独立演示（含 full 模拟桌面），PyQt 生产路径请运行 python main.py")
    webbrowser.open(url)

    try:
        thread.join()
    except KeyboardInterrupt:
        httpd.shutdown()
        print("\n[HAJIMI] 已停止")


if __name__ == "__main__":
    main()
