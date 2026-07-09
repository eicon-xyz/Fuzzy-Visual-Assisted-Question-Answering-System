# -*- coding: utf-8 -*-
"""
HAJIMI —— Web 端「用户管理」测试数据注入
=========================================
向 A 端活动数据库（HAJIMI_UI/data/hajimi.db）写入若干用户，
并为其挂接事务 / 反馈 / 失败记录，使用户列表的任务数与统计抽屉有真实数据。

用法（在 HAJIMI_UI 目录下运行，确保写入的是服务端在用的库）::

    cd E:\\Fuzzy-Visual-Assisted-Question-Answering-System\\HAJIMI_UI
    python -m scripts.seed_users        # 若放在 scripts/ 下
    # 或直接：
    python seed_users.py
"""
import hashlib
import os
import random
import sys

# 以 HAJIMI_UI 为工作目录，保证使用服务端同一个 SQLite 库
HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(HERE, "server")):
    ROOT = HERE
else:  # 允许从 scripts/ 或其它位置运行
    ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from datetime import datetime, timedelta, timezone

from server.database import SessionLocal, init_db
from server.database.models import User, Transaction, Feedback, Failure


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# 待注入用户：(用户名, 角色, 注册天数前, 最后登录天数前 或 None=从未登录, 初始密码)
USERS = [
    ("zhangwei",  "admin", 45, 0,    "123456"),
    ("lina",      "user",  38, 1,    "123456"),
    ("wangfang",  "user",  30, 2,    "123456"),
    ("liuyang",   "user",  25, 5,    "123456"),
    ("chenjing",  "user",  20, None, "123456"),
    ("zhaolei",   "user",  12, 0,    "123456"),
    ("sunqian",   "admin", 8,  3,    "123456"),
    ("zhoujie",   "user",  3,  None, "123456"),
]

INTENTS = ["operation_guide", "ui_navigation", "element_cognition", "error_diagnosis",
           "content_cognition", "file_management", "proactive_alert",
           "tutorial_generation", "emotion_comfort"]
QUERIES = ["安装微信到D盘", "打开浏览器访问官网", "把这张图另存为", "这个按钮是干什么的",
           "调高屏幕亮度", "保存当前文档", "内存不足怎么处理", "帮我做个操作教程",
           "连接蓝牙耳机", "清理回收站"]
SUMMARIES = ["安装软件", "打开应用", "保存文件", "元素认知", "系统设置",
             "文件管理", "错误诊断", "教程生成", "设备连接", "系统清理"]
# 结果分布：偏成功
RESULTS = ["success"] * 7 + ["fail", "cancel", "redirect"]


def _now():
    return datetime.now(timezone.utc)


def seed():
    init_db()
    db = SessionLocal()
    created_users = 0
    created_tx = 0
    created_fb = 0
    created_fail = 0

    try:
        for username, role, reg_days, login_days, pw in USERS:
            user = db.query(User).filter(User.username == username).first()
            if user is None:
                user = User(
                    username=username,
                    password_hash=_hash(pw),
                    role=role,
                    created_at=_now() - timedelta(days=reg_days),
                    last_login_at=(None if login_days is None
                                   else _now() - timedelta(days=login_days)),
                )
                db.add(user)
                db.flush()  # 拿到 user_id
                created_users += 1
            else:
                # 已存在则只补齐时间字段，避免重复插入
                user.role = role
                user.created_at = _now() - timedelta(days=reg_days)
                user.last_login_at = (None if login_days is None
                                      else _now() - timedelta(days=login_days))

            # 为该用户挂接若干事务（不同用户任务量不同）
            n_tasks = random.randint(3, 14)
            for _ in range(n_tasks):
                idx = random.randrange(len(QUERIES))
                result = random.choice(RESULTS)
                plan_type = random.choice(["L2", "L2", "L3"])
                tx = Transaction(
                    user_id=user.user_id,
                    timestamp=_now() - timedelta(hours=random.randint(1, 24 * reg_days or 1)),
                    intent_category=random.choice(INTENTS),
                    user_query=QUERIES[idx],
                    intent_summary=SUMMARIES[idx],
                    plan_type=plan_type,
                    complexity_score=random.randint(10, 90),
                    result=result,
                    duration_ms=random.randint(1200, 9000),
                    redline_triggered=False,
                )
                db.add(tx)
                db.flush()
                created_tx += 1

                # 部分成功任务给一条反馈
                if result == "success" and random.random() < 0.4:
                    db.add(Feedback(
                        task_id=tx.task_id,
                        user_id=user.user_id,
                        feedback_type=random.choice(["useful", "useful", "neutral"]),
                        comment=random.choice(["很有用", "步骤清晰", "还行", ""]),
                    ))
                    created_fb += 1

                # 失败任务补一条失败归因
                if result == "fail":
                    db.add(Failure(
                        task_id=tx.task_id,
                        failure_type=random.choice(
                            ["element_not_found", "step_timeout", "llm_parse_error"]),
                        step_index=random.randint(1, 5),
                        error_detail="自动生成的演示失败记录",
                    ))
                    created_fail += 1

        db.commit()
    finally:
        db.close()

    print("用户注入完成：")
    print(f"  新建用户   : {created_users}")
    print(f"  事务       : {created_tx}")
    print(f"  反馈       : {created_fb}")
    print(f"  失败记录   : {created_fail}")
    print("数据库       : HAJIMI_UI/data/hajimi.db")
    print("提示：用户初始密码均为 123456；可在 Web 端『用户管理』查看/重置/删除。")


if __name__ == "__main__":
    seed()
