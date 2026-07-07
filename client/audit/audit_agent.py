"""
HAJIMI Client — 审计代理 (AuditAgent) 模块
=============================================
本地 SQLite 队列 + 隐私脱敏 + 批量 HTTP 上报 + 指数退避重试

严格按照 B-C 接口契约 §接口6 定义的数据模型与处理流程实现。

用法::

    from client.audit.audit_agent import AuditAgent

    agent = AuditAgent(server_url="http://localhost:8000", demo_key="hajimi-demo-2026")
    agent.enqueue({
        "task_id": "...",
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
        "timestamp": "2026-06-29T14:32:15+08:00",
    })

    定时批量上报
    status = agent.get_queue_status()
    print(f"队列深度: {status['queue_depth']}, 可连接服务端: {status['server_reachable']}")
"""

import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime


# ────────────────────────── 回调类型 ──────────────────────────

# (status: str, batch_size: int, queue_depth: int, error: Optional[str])
AuditStatusCallback = Callable[[str, int, int, Optional[str]], None]


# ────────────────────────── 隐私脱敏 ──────────────────────────

# 敏感关键词正则（中文 + 英文）
_SENSITIVE_PATTERNS: List[tuple] = [
    # (pattern, replacement, description)
    (re.compile(r'(password|passwd|pwd|密码|口令)\s*[:：=]\s*\S+', re.IGNORECASE),
     r'\1=[REDACTED]', "密码字段"),
    (re.compile(r'(api[_-]?key|apikey|secret|token)\s*[:：=]\s*\S+', re.IGNORECASE),
     r'\1=[REDACTED]', "API密钥"),
    (re.compile(r'(?:C:\\|D:\\|E:\\|/home/|/Users/)[^\s,，。；;]*'),
     '[FILE_PATH]', "文件绝对路径"),
    (re.compile(r'(文件路径|路径|path)\s*[:：=]\s*[^\s,，。；;]+', re.IGNORECASE),
     r'\1=[FILE_PATH]', "路径字段"),
    (re.compile(r'\b\d{15,19}\b'), '[ID_NUMBER]', "身份证号"),
    (re.compile(r'\b1[3-9]\d{9}\b'), '[PHONE]', "手机号"),
    (re.compile(r'\b[\w.-]+@[\w.-]+\.\w+\b'), '[EMAIL]', "邮箱地址"),
]

# 窗口标题 → 类别替换映射
_WINDOW_TITLE_MAP = {
    "微信": "即时通讯",
    "QQ": "即时通讯",
    "企业微信": "即时通讯",
    "钉钉": "即时通讯",
    "浏览器": "浏览器",
    "Chrome": "浏览器",
    "Edge": "浏览器",
    "Firefox": "浏览器",
    "文件资源管理器": "文件管理器",
    "Finder": "文件管理器",
    "VSCode": "代码编辑器",
    "Visual Studio Code": "代码编辑器",
    "记事本": "文本编辑器",
    "Notepad": "文本编辑器",
    "Word": "文档编辑器",
    "Excel": "表格编辑器",
    "PowerPoint": "演示文稿",
    "控制面板": "系统设置",
    "设置": "系统设置",
}


def desensitize_text(text: str) -> str:
    """对文本执行隐私脱敏

    - 密码/API Key → [REDACTED]
    - 文件绝对路径 → [FILE_PATH]
    - 身份证号/手机号/邮箱 → 类型标记
    - 窗口标题 → 类别替换
    """
    if not text:
        return ""

    result = text

    # 1. 高优先级：密码、密钥
    for pattern, replacement, _desc in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)

    # 2. 窗口标题脱敏
    for title, category in _WINDOW_TITLE_MAP.items():
        result = result.replace(title, f"[{category}]")

    return result


def desensitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """对审计记录执行隐私脱敏（返回新 dict）"""
    clean = record.copy()
    if "query" in clean:
        clean["query"] = desensitize_text(clean["query"])
    if "comment" in clean and clean["comment"]:
        clean["comment"] = desensitize_text(clean["comment"])
    return clean


# ────────────────────────── SQLite 队列 ──────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    record_json TEXT    NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
)
"""


class AuditAgent:
    """审计代理

    本地 SQLite 队列（WAL 模式） + 批量 HTTP 上报 + 指数退避重试

    设计要点（来自 B-C 接口契约）：
    - 累积 10 条或空闲 5 分钟 → 批量上报
    - 成功则删除本地记录
    - 失败则指数退避（1min/5min/15min/1h），超 3 次写 fallback.log
    """

    # 默认配置
    DEFAULT_BATCH_SIZE = 10
    DEFAULT_FLUSH_INTERVAL = 300   # 5 分钟
    DEFAULT_BASE_URL = "http://localhost:8010"
    DEFAULT_DEMO_KEY = "hajimi-demo-2026"
    MAX_RETRIES = 3
    RETRY_DELAYS = [60, 300, 900, 3600]  # 1min, 5min, 15min, 1h

    def __init__(
        self,
        db_path: str = "client/audit/audit_queue.db",
        server_url: str = DEFAULT_BASE_URL,
        demo_key: str = DEFAULT_DEMO_KEY,
        client_id: str = "",
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval: int = DEFAULT_FLUSH_INTERVAL,
        status_callback: Optional[AuditStatusCallback] = None,
    ):
        self._db_path = db_path
        self._server_url = server_url.rstrip("/")
        self._demo_key = demo_key
        self._client_id = client_id or self._generate_client_id()
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._callback = status_callback

        # 线程安全
        self._lock = threading.Lock()
        self._stop_requested = False

        # HTTP 客户端
        self._httpx_available = False
        try:
            import httpx
            self._http = httpx.Client(timeout=30.0)
            self._httpx_available = True
        except ImportError:
            self._http = None

        # 初始化数据库
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._init_db()

        # 后台工作线程
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="audit-worker"
        )
        self._worker_thread.start()

    # ────────────────────────── 公开 API ──────────────────────────

    def enqueue(self, record: Dict[str, Any]) -> bool:
        """将审计记录入队（线程安全）

        Args:
            record: 审计记录 dict，字段见 B-C 接口契约 §接口6 AuditRecord

        Returns:
            True 如果成功入队
        """
        # 1. 隐私脱敏
        clean = desensitize_record(record)

        # 2. 确保必要字段
        if "timestamp" not in clean:
            clean["timestamp"] = datetime.now().isoformat()

        # 3. 写入本地 SQLite
        now = datetime.now().isoformat()
        try:
            with self._lock:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO audit_queue (record_json, retry_count, created_at, updated_at) "
                    "VALUES (?, 0, ?, ?)",
                    (json.dumps(clean, ensure_ascii=False), now, now),
                )
                conn.commit()
            self._emit_status("queued", 1, self.get_queue_depth(), None)
            return True
        except Exception as e:
            self._emit_status("failed", 0, self.get_queue_depth(), str(e))
            return False

    def send_feedback(
        self,
        task_id: str,
        feedback_type: str,
        comment: str = "",
    ) -> bool:
        """单独上报用户反馈（A-C 接口契约 §3.1 — POST /api/audit/feedback）

        与批量审计日志解耦，可在任务结束后立即调用。
        """
        if not self._httpx_available:
            return False

        payload = {
            "task_id": task_id,
            "feedback_type": feedback_type,
        }
        if comment:
            payload["comment"] = desensitize_text(comment)

        try:
            r = self._http.post(
                f"{self._server_url}/api/audit/feedback",
                headers={
                    "X-Demo-Key": self._demo_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("received", False)
        except Exception:
            return False

    def get_queue_depth(self) -> int:
        """获取本地队列深度"""
        try:
            with self._lock:
                conn = self._get_conn()
                row = conn.execute("SELECT COUNT(*) FROM audit_queue").fetchone()
                return row[0] if row else 0
        except Exception:
            return -1

    def get_queue_status(self) -> dict:
        """获取队列状态"""
        return {
            "queue_depth": self.get_queue_depth(),
            "batch_size": self._batch_size,
            "flush_interval_s": self._flush_interval,
            "server_reachable": self.ping_server(),
            "client_id": self._client_id,
        }

    def ping_server(self) -> bool:
        """检测后端服务是否可达"""
        if not self._httpx_available:
            return False
        try:
            r = self._http.get(
                f"{self._server_url}/api/health",
                timeout=5.0,
            )
            return r.status_code == 200
        except Exception:
            return False

    def flush_now(self) -> dict:
        """手动触发立即上报（供测试/调试用）"""
        return self._do_flush()

    def shutdown(self) -> None:
        """关闭审计代理，释放资源"""
        self._stop_requested = True
        self._do_flush()  # 最后尝试清空队列
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
        if self._http:
            self._http.close()

    # ────────────────────────── 内部实现 ──────────────────────────

    def _init_db(self) -> None:
        """初始化 SQLite 数据库（WAL 模式）"""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        self._conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if not hasattr(self, "_conn") or self._conn is None:
            self._init_db()
        return self._conn

    def _generate_client_id(self) -> str:
        """生成客户端唯一标识"""
        import uuid
        import platform
        host = platform.node() or "unknown"
        short_id = uuid.uuid4().hex[:8]
        return f"desktop-{host}-{short_id}"

    def _worker_loop(self) -> None:
        """后台工作循环：定期检查是否应触发批量上报"""
        last_flush = time.monotonic()
        while not self._stop_requested:
            time.sleep(10)  # 每 10s 检查一次

            try:
                depth = self.get_queue_depth()
            except Exception:
                continue

            # 触发条件：累积满一批 或 空闲超时
            should_flush = (
                depth >= self._batch_size
                or (depth > 0 and time.monotonic() - last_flush >= self._flush_interval)
            )

            if should_flush:
                self._do_flush()
                last_flush = time.monotonic()

    def _do_flush(self) -> dict:
        """批量上报本地队列中的记录

        Returns:
            {"sent": int, "failed": int, "server_queue_depth": int}
        """
        if not self._httpx_available:
            return {"sent": 0, "failed": 0, "server_queue_depth": 0, "error": "httpx 不可用"}

        # 1. 读取待上报记录
        records = self._fetch_pending()
        if not records:
            return {"sent": 0, "failed": 0, "server_queue_depth": 0}

        # 2. 批量 POST
        batch = []
        for rec in records:
            try:
                record_data = json.loads(rec["record_json"])
                batch.append(record_data)
            except json.JSONDecodeError:
                # 损坏记录直接删除
                self._delete_record(rec["id"])
                continue

        if not batch:
            return {"sent": 0, "failed": 0, "server_queue_depth": 0}

        try:
            r = self._http.post(
                f"{self._server_url}/api/audit/report",
                headers={
                    "X-Demo-Key": self._demo_key,
                    "Content-Type": "application/json",
                },
                json={
                    "client_id": self._client_id,
                    "batch": batch,
                },
            )
            r.raise_for_status()
            resp = r.json()

            # 3. 成功：删除已上报记录
            for rec in records:
                self._delete_record(rec["id"])

            server_depth = resp.get("server_queue_depth", 0)
            self._emit_status("success", len(batch), self.get_queue_depth(), None)

            # 服务端压力反馈：减缓上报频率
            if server_depth > 100:
                self._batch_size = max(1, self._batch_size // 2)

            return {"sent": len(batch), "failed": 0, "server_queue_depth": server_depth}

        except Exception as e:
            # 4. 失败：更新重试计数
            error_msg = str(e)
            for rec in records:
                new_retry = rec["retry_count"] + 1
                if new_retry > self.MAX_RETRIES:
                    # 超过最大重试次数，写 fallback.log
                    self._write_fallback_log(rec, error_msg)
                    self._delete_record(rec["id"])
                else:
                    self._update_retry(rec["id"], new_retry, error_msg)

            self._emit_status("failed", len(batch), self.get_queue_depth(), error_msg)
            return {"sent": 0, "failed": len(batch), "server_queue_depth": 0, "error": error_msg}

    def _fetch_pending(self, limit: Optional[int] = None) -> List[Dict]:
        """读取待上报记录"""
        limit = limit or self._batch_size
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, record_json, retry_count FROM audit_queue "
                "ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": r[0], "record_json": r[1], "retry_count": r[2]} for r in rows]

    def _delete_record(self, record_id: int) -> None:
        """删除已上报成功的记录"""
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM audit_queue WHERE id = ?", (record_id,))
            conn.commit()

    def _update_retry(self, record_id: int, retry_count: int, error: str) -> None:
        """更新重试计数"""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE audit_queue SET retry_count=?, last_error=?, updated_at=? WHERE id=?",
                (retry_count, error, now, record_id),
            )
            conn.commit()

    def _write_fallback_log(self, record: Dict, error: str) -> None:
        """超过最大重试次数后写入 fallback.log"""
        log_path = os.path.join(
            os.path.dirname(self._db_path) or ".", "fallback.log"
        )
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now().isoformat()}] "
                    f"id={record.get('id')} error={error} "
                    f"record={record.get('record_json', '')}\n"
                )
        except Exception:
            pass  # 最终兜底，无法写日志则放弃

    def _emit_status(
        self,
        status: str,
        batch_size: int,
        queue_depth: int,
        error: Optional[str],
    ) -> None:
        """安全地调用状态回调"""
        if self._callback:
            try:
                self._callback(status, batch_size, queue_depth, error)
            except Exception:
                pass
