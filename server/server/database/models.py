"""
HAJIMI 数据库 ORM 模型（7 张表）

参考：设计文档 §4.6.1
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from server.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────── t_users ──────────────────────────

class User(Base):
    __tablename__ = "t_users"

    user_id = Column(String(64), primary_key=True, default=_new_uuid)
    username = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)  # bcrypt
    role = Column(String(16), nullable=False, default="user")  # user | admin
    preferences = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)
    last_login_at = Column(DateTime, nullable=True)


# ────────────────────────── t_transactions ──────────────────────────

class Transaction(Base):
    __tablename__ = "t_transactions"

    task_id = Column(String(64), primary_key=True, default=_new_uuid)
    user_id = Column(String(64), ForeignKey("t_users.user_id"), nullable=True)
    timestamp = Column(DateTime, default=_now, index=True)
    intent_category = Column(String(32), nullable=False, index=True)
    user_query = Column(String(500), nullable=False)
    intent_summary = Column(String(256), nullable=False)
    reference_type = Column(String(16), nullable=True)
    plan_type = Column(String(8), nullable=False, default="L3")  # L2 | L3
    complexity_score = Column(Integer, default=0)
    blueprint_json = Column(JSON, nullable=True)
    result = Column(String(16), nullable=True)  # success | fail | cancel | redirect | rejected
    duration_ms = Column(Integer, nullable=True)
    clarification_count = Column(Integer, default=0)

    # 审计扩展字段
    redline_triggered = Column(Boolean, default=False)
    redline_category = Column(String(32), nullable=True)
    element_count = Column(Integer, nullable=True)
    detection_latency_ms = Column(Integer, nullable=True)

    # 关联
    step_logs = relationship("StepLog", back_populates="transaction", cascade="all, delete-orphan")
    feedbacks = relationship("Feedback", back_populates="transaction", cascade="all, delete-orphan")


# ────────────────────────── t_step_logs ──────────────────────────

class StepLog(Base):
    __tablename__ = "t_step_logs"

    log_id = Column(String(64), primary_key=True, default=_new_uuid)
    task_id = Column(String(64), ForeignKey("t_transactions.task_id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    action = Column(String(256), nullable=False)
    target_element_id = Column(String(16), nullable=True)
    target_bbox = Column(JSON, nullable=True)  # [x1, y1, x2, y2]
    status = Column(String(16), nullable=False, default="pending")
    fingerprint_before = Column(String(64), nullable=True)
    fingerprint_after = Column(String(64), nullable=True)
    fingerprint_match = Column(Boolean, nullable=True)
    error_code = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=_now)

    transaction = relationship("Transaction", back_populates="step_logs")


# ────────────────────────── t_feedback ──────────────────────────

class Feedback(Base):
    __tablename__ = "t_feedback"

    feedback_id = Column(String(64), primary_key=True, default=_new_uuid)
    task_id = Column(String(64), ForeignKey("t_transactions.task_id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("t_users.user_id"), nullable=True)
    feedback_type = Column(String(16), nullable=False)  # useful | useless | neutral
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, index=True)

    transaction = relationship("Transaction", back_populates="feedbacks")


# ────────────────────────── t_failures ──────────────────────────

class Failure(Base):
    __tablename__ = "t_failures"

    failure_id = Column(String(64), primary_key=True, default=_new_uuid)
    task_id = Column(String(64), nullable=False, index=True)
    failure_type = Column(String(64), nullable=False, index=True)
    step_index = Column(Integer, nullable=True)
    fingerprint_hash = Column(String(64), nullable=True)
    llm_snapshot = Column(Text, nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now, index=True)


# ────────────────────────── t_system_configs ──────────────────────────

class SystemConfig(Base):
    __tablename__ = "t_system_configs"

    config_id = Column(String(64), primary_key=True, default=_new_uuid)
    config_key = Column(String(128), unique=True, nullable=False, index=True)
    config_value = Column(JSON, nullable=False)
    description = Column(String(256), nullable=True)
    updated_by = Column(String(64), ForeignKey("t_users.user_id"), nullable=True)
    updated_at = Column(DateTime, default=_now)


# ────────────────────────── t_redline_logs ──────────────────────────

class RedlineLog(Base):
    """红线拦截日志（第 7 张表）"""
    __tablename__ = "t_redline_logs"

    log_id = Column(String(64), primary_key=True, default=_new_uuid)
    query = Column(String(500), nullable=False)
    category = Column(String(32), nullable=False, index=True)  # physical_operation | personal_privacy | realtime_dynamic
    action = Column(String(16), nullable=False)  # reject | guided_reject | degrade
    message = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=_now, index=True)
