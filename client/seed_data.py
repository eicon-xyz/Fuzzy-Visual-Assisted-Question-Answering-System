"""
HAJIMI — 管理面板测试数据注入脚本
====================================
向 A 端数据库写入模拟数据，使 Web 管理面板展示真实可操作的图表。

用法::

    python client/seed_data.py
"""

import sys, os, random, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from datetime import datetime, timedelta
sys.path.insert(0, ".")

from server.database import SessionLocal, init_db
from server.database.models import Transaction, Feedback, Failure, SystemConfig, RedlineLog


def seed():
    init_db()
    db = SessionLocal()

    # ── 系统配置 ──
    if db.query(SystemConfig).count() == 0:
        configs = [
            ("version", "v2.2.0"),
            ("llm_provider", "deepseek"),
            ("confidence_threshold", 80),
            ("max_blueprint_steps", 15),
            ("config_pull_interval_min", 30),
            ("audit_batch_size", 10),
            ("offline_tts_engine", "pyttsx3"),
            ("routing_rules", {"length_weight":0.3,"verb_weight":8,"cross_app_bonus":10,"threshold_score":30,"custom_keywords":["安装","配置","设置"]}),
        ]
        for key, val in configs:
            db.add(SystemConfig(config_key=key, config_value=val))
        print(f"  SystemConfig: {len(configs)} rows")

    # ── 事务数据 ──
    intents = ["operation_guide", "ui_navigation", "element_cognition", "error_diagnosis",
               "content_cognition", "file_management", "proactive_alert", "tutorial_generation", "emotion_comfort"]
    queries = ["安装微信", "打开浏览器", "截屏保存", "这个按钮是什么意思", "怎么调亮度",
               "保存文档", "内存不足警告", "制作教程", "卡住了怎么办"]
    results = ["success"] * 7 + ["fail", "cancel", "redirect"]

    for i in range(50):
        t = datetime.now() - timedelta(hours=random.randint(0, 72))
        tx = Transaction(
            task_id=f"seed-{i:04d}",
            user_query=random.choice(queries),
            intent_category=random.choice(intents),
            intent_summary=random.choice(queries),
            plan_type=random.choice(["L2","L3"]),
            complexity_score=random.randint(10, 60),
            result=random.choice(results),
            duration_ms=random.randint(500, 60000),
            redline_triggered=random.random() < 0.08,
            timestamp=t,
        )
        db.add(tx)
    print(f"  Transaction: 50 rows ({datetime.now().strftime('%H:%M:%S')})")

    # ── 反馈 ──
    feedbacks = [("useful", "指引清晰"), ("useless", "没帮上忙"), ("neutral", "")]
    txs = db.query(Transaction).limit(30).all()
    for tx in txs:
        if random.random() < 0.7:
            fbt, comment = random.choice(feedbacks)
            db.add(Feedback(task_id=tx.task_id, feedback_type=fbt, comment=comment))
    print(f"  Feedback: {len(txs)} rows")

    # ── 失败记录 ──
    fail_types = [
        ("blueprint_mismatch", "蓝图不匹配"),
        ("llm_timeout", "LLM 超时"),
        ("parse_error", "解析错误"),
        ("redline_blocked", "红线拦截"),
        ("user_abort", "用户中止"),
    ]
    failed_txs = db.query(Transaction).filter(Transaction.result.in_(["fail","cancel"])).all()
    for tx in failed_txs:
        ft, flabel = random.choice(fail_types)
        db.add(Failure(
            task_id=tx.task_id,
            failure_type=ft,
            step_index=random.randint(1, 3),
            error_detail=f"Mock error: {flabel} at step {random.randint(1,3)}",
        ))
    print(f"  Failure: {len(failed_txs)} rows")

    # ── 红线日志 ──
    for i in range(5):
        db.add(RedlineLog(
            query=random.choice(["帮我自动抢票", "扫描硬盘所有文件", "删除系统文件"]),
            category=random.choice(["physical_operation", "personal_privacy", "realtime_dynamic"]),
            action="reject",
            message=f"红线拦截 #{i+1}: 检测到不安全操作请求",
        ))
    print(f"  RedlineLog: 5 rows")

    db.commit()
    db.close()
    print("\n  数据注入完成！Web 面板设置 setUseMock(false) 即可看到真实数据")


if __name__ == "__main__":
    seed()
