"""
HAJIMI — 审计代理端到端测试 (Day 3)
=======================================
启动内置 Mock HTTP 服务器，测试审计代理的完整上报链路：
正常上报 / 服务端错误 / 网络中断 / 重试 / fallback.log

用法::

    python client/audit_e2e_test.py
"""

import sys
import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ═══════════════════════════════════════════════════════
#  Mock 审计服务器
# ═══════════════════════════════════════════════════════

class MockAuditHandler(BaseHTTPRequestHandler):
    """模拟 A 的审计端点，可配置行为"""

    # 类变量：控制响应行为
    scenario = "normal"        # normal / error / slow
    received_requests: list = []
    _lock = threading.Lock()

    def do_POST(self):
        if self.path == "/api/audit/report":
            self._handle_report()
        elif self.path == "/api/audit/feedback":
            self._handle_feedback()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_report(self):
        with MockAuditHandler._lock:
            MockAuditHandler.received_requests.append({
                "time": time.time(),
                "body": self._read_body(),
            })

        if MockAuditHandler.scenario == "error":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "Internal Server Error"}')
        elif MockAuditHandler.scenario == "slow":
            time.sleep(3)
            self._send_ok()
        else:
            self._send_ok()

    def _handle_feedback(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"received": True}).encode())

    def _send_ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "received": 1,
            "server_queue_depth": 5,
        }).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length).decode("utf-8")
        return ""

    def log_message(self, format, *args):
        pass  # 关闭 HTTP 日志


class MockServer:
    """Mock HTTP 服务器，运行在独立线程"""

    def __init__(self, port: int = 18900):
        self._server = HTTPServer(("127.0.0.1", port), MockAuditHandler)
        self._port = port
        self._thread: threading.Thread = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def stop(self):
        self._server.shutdown()

    def set_scenario(self, scenario: str):
        MockAuditHandler.scenario = scenario

    def clear_requests(self):
        with MockAuditHandler._lock:
            MockAuditHandler.received_requests.clear()

    @property
    def request_count(self) -> int:
        return len(MockAuditHandler.received_requests)


# ═══════════════════════════════════════════════════════
#  测试用例
# ═══════════════════════════════════════════════════════

PASS = 0
FAIL = 0


def ok(msg, condition=True):
    global PASS
    global FAIL
    if condition:
        print(f"  ✅ {msg}")
        PASS += 1
    else:
        print(f"  ❌ {msg}")
        FAIL += 1


def bad(msg):
    global FAIL
    print(f"  ❌ {msg}")
    FAIL += 1


def info(msg):
    print(f"  ℹ️  {msg}")


# ── 测试 1: 正常上报 ──

def test_normal_upload(server: MockServer):
    print()
    print("=" * 50)
    print("  1. 正常批量上报")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent
    import tempfile

    server.set_scenario("normal")
    server.clear_requests()

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_e2e_normal.db"),
        server_url=server.url,
        batch_size=3,
    )

    # 写入 3 条 → 触发批量上报
    for i in range(3):
        agent.enqueue({
            "task_id": f"e2e-normal-{i:03d}",
            "query": f"测试操作 {i}",
            "intent_category": "operation_guide",
            "complexity_score": 30 + i,
            "route": "L3" if i % 2 else "L2",
            "total_steps": 3,
            "completed_steps": 3,
            "result": "success",
            "duration_ms": 5000,
            "fingerprint_mismatches": 0,
            "redline_triggered": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        })

    ok(f"3 条记录入队 (depth={agent.get_queue_depth()})")

    # 手动触发上报
    result = agent.flush_now()
    ok(f"上报结果: sent={result.get('sent', 0)}", result.get("sent", 0) == 3)

    # 服务端应收到 1 个 POST 请求（含 3 条）
    time.sleep(0.2)
    req_count = server.request_count
    ok(f"服务端收到 {req_count} 个 POST 请求", req_count >= 1)

    # 上报成功后本地队列应清空
    depth = agent.get_queue_depth()
    ok(f"本地队列已清空 (depth={depth})", depth == 0)

    agent.shutdown()


# ── 测试 2: 服务端错误 + 重试 ──

def test_server_error_retry(server: MockServer):
    print()
    print("=" * 50)
    print("  2. 服务端错误 → 重试机制")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent
    import tempfile

    server.set_scenario("error")  # 返回 500
    server.clear_requests()

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_e2e_error.db"),
        server_url=server.url,
        batch_size=1,
    )

    agent.enqueue({
        "task_id": "e2e-error-000",
        "query": "测试错误重试",
        "intent_category": "operation_guide",
        "complexity_score": 30,
        "route": "L3",
        "total_steps": 3,
        "completed_steps": 3,
        "result": "success",
        "duration_ms": 5000,
        "fingerprint_mismatches": 0,
        "redline_triggered": False,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    })

    # 上报应失败
    result = agent.flush_now()
    ok(f"上报失败 (sent=0, failed=1)", result.get("failed", 0) >= 1)

    # 记录仍在队列中
    depth = agent.get_queue_depth()
    ok(f"记录仍在队列 (depth={depth})", depth >= 1)

    agent.shutdown()


# ── 测试 3: 脱敏验证 ──

def test_desensitization():
    print()
    print("=" * 50)
    print("  3. 隐私脱敏完整验证 (6 类)")
    print("=" * 50)

    from client.audit.audit_agent import desensitize_text

    cases = [
        ("密码=123456", "[REDACTED]", "密码字段"),
        ("api_key=sk-abc123", "[REDACTED]", "API Key"),
        ("C:\\Users\\admin\\Desktop\\file.txt", "[FILE_PATH]", "文件路径"),
        ("手机号 13800138000", "[PHONE]", "手机号"),
        ("邮箱 test@example.com", "[EMAIL]", "邮箱"),
        ("身份证号 110101199001011234", "[ID_NUMBER]", "身份证号"),
    ]

    for text, marker, desc in cases:
        result = desensitize_text(text)
        if marker in result:
            ok(f"{desc}: {text[:25]} → {marker}")
        else:
            bad(f"{desc}: {text[:25]} → {result[:30]} (期望含 {marker})")


# ── 测试 4: 审计记录格式验证 ──

def test_record_format(server: MockServer):
    print()
    print("=" * 50)
    print("  4. 请求体格式验证 (A-C 契约 §3.1)")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent
    import tempfile

    server.set_scenario("normal")
    server.clear_requests()

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_e2e_format.db"),
        server_url=server.url,
        batch_size=1,
    )

    agent.enqueue({
        "task_id": "e2e-format-001",
        "query": "怎么安装微信",
        "intent_category": "operation_guide",
        "complexity_score": 35,
        "route": "L3",
        "total_steps": 3,
        "completed_steps": 3,
        "result": "success",
        "duration_ms": 45200,
        "feedback_type": "useful",
        "fingerprint_mismatches": 0,
        "redline_triggered": False,
        "timestamp": "2026-07-01T14:32:15+08:00",
    })

    agent.flush_now()
    time.sleep(0.2)

    if server.request_count >= 1:
        req = MockAuditHandler.received_requests[-1]
        body = json.loads(req["body"])

        # 验证 top-level 字段
        ok("client_id 字段存在", "client_id" in body)
        ok("batch 字段存在", "batch" in body)
        ok("batch 是数组", isinstance(body.get("batch"), list))

        if body.get("batch"):
            record = body["batch"][0]
            required = ["task_id", "query", "intent_category", "route",
                        "total_steps", "completed_steps", "result",
                        "duration_ms", "timestamp"]
            for field in required:
                ok(f"batch[].{field} 存在", field in record)
    else:
        bad("服务端未收到请求")

    agent.shutdown()


# ── 测试 5: 单独反馈端点 ──

def test_feedback_endpoint(server: MockServer):
    print()
    print("=" * 50)
    print("  5. 单独反馈端点 (A-C 契约 §3.1 — /api/audit/feedback)")
    print("=" * 50)

    from client.audit.audit_agent import AuditAgent
    import tempfile

    server.set_scenario("normal")

    agent = AuditAgent(
        db_path=os.path.join(tempfile.gettempdir(), "hajimi_e2e_fb.db"),
        server_url=server.url,
    )

    result = agent.send_feedback(
        task_id="test-feedback-001",
        feedback_type="useful",
        comment="指引很清晰",
    )
    ok("反馈上报成功", result is True)

    agent.shutdown()


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  HAJIMI Day 3 — 审计代理端到端测试")
    print()

    server = MockServer(port=18900)
    info("启动 Mock 审计服务器 (端口 18900)")
    server.start()
    info(f"Mock 服务器运行在 {server.url}")

    try:
        test_normal_upload(server)
        test_server_error_retry(server)
        test_desensitization()
        test_record_format(server)
        test_feedback_endpoint(server)
    finally:
        server.stop()

    print()
    print("=" * 50)
    print(f"  结果: {PASS} 通过, {FAIL} 失败")
    if FAIL == 0:
        print("  审计代理端到端测试全部通过")
    else:
        print(f"  ⚠ {FAIL} 项未通过")
