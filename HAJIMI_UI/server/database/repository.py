"""
HAJIMI 数据仓库层

提供高层 CRUD 操作，供路由和服务层调用。
"""
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session

from server.database import SessionLocal
from server.database.models import (
    Transaction, StepLog, Feedback, Failure, SystemConfig, RedlineLog,
)
from server.models.schemas import ProcessResponse


class TaskRepository:
    """任务事务仓库"""

    @staticmethod
    def create_from_response(
        response: ProcessResponse,
        query: str,
        db: Optional[Session] = None,
    ) -> Transaction:
        """从 ProcessResponse 创建事务记录"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            txn = Transaction(
                task_id=response.task_id,
                intent_category=response.intent.category,
                user_query=query,
                intent_summary=response.intent.summary,
                reference_type=response.intent.reference_type,
                plan_type=response.detection_meta.get("route", "L3") if response.detection_meta else "L3",
                complexity_score=response.detection_meta.get("complexity", 0) if response.detection_meta else 0,
                blueprint_json={
                    "name": response.blueprint.name,
                    "total_steps": response.blueprint.total_steps,
                    "state": response.blueprint.state,
                },
                element_count=response.detection_meta.get("element_count") if response.detection_meta else None,
                detection_latency_ms=response.detection_meta.get("latency_ms") if response.detection_meta else None,
                redline_triggered=response.redline is not None and response.redline.triggered,
                redline_category=response.redline.category if response.redline else None,
                result="rejected" if (response.redline and response.redline.triggered) else None,
                clarification_count=1 if response.intent.needs_clarification else 0,
            )

            # 记录步骤日志
            for step in response.steps:
                step_log = StepLog(
                    task_id=response.task_id,
                    step_index=step.step_index,
                    action=step.action,
                    target_element_id=step.target_element_id,
                    target_bbox=step.annotation.highlight_bbox if step.annotation else None,
                    status=step.status,
                )
                db.add(step_log)

            db.add(txn)
            db.commit()
            db.refresh(txn)
            return txn
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_result(
        task_id: str,
        result: str,
        duration_ms: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> None:
        """更新任务结果"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            txn = db.query(Transaction).filter(Transaction.task_id == task_id).first()
            if txn:
                txn.result = result
                if duration_ms is not None:
                    txn.duration_ms = duration_ms
                db.commit()
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_stats_overview(db: Optional[Session] = None) -> dict:
        """获取仪表盘总览统计"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            total = db.query(Transaction).count()
            success_count = db.query(Transaction).filter(Transaction.result == "success").count()
            fail_count = db.query(Transaction).filter(Transaction.result == "fail").count()
            rejected_count = db.query(Transaction).filter(Transaction.result == "rejected").count()
            l2_count = db.query(Transaction).filter(Transaction.plan_type == "L2").count()
            l3_count = db.query(Transaction).filter(Transaction.plan_type == "L3").count()

            return {
                "total_transactions": total,
                "success_count": success_count,
                "fail_count": fail_count,
                "rejected_count": rejected_count,
                "success_rate": round(success_count / total, 3) if total > 0 else 0.0,
                "l2_count": l2_count,
                "l3_count": l3_count,
                "l2_ratio": round(l2_count / total, 3) if total > 0 else 0.0,
            }
        finally:
            if close_db:
                db.close()


class RedlineRepository:
    """红线拦截日志仓库"""

    @staticmethod
    def log(query: str, category: str, action: str, message: str, db: Optional[Session] = None) -> RedlineLog:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            log_entry = RedlineLog(
                query=query,
                category=category,
                action=action,
                message=message,
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            return log_entry
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_stats(db: Optional[Session] = None) -> dict:
        """红线拦截统计"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            from sqlalchemy import func
            total = db.query(RedlineLog).count()
            by_category = (
                db.query(RedlineLog.category, func.count(RedlineLog.log_id))
                .group_by(RedlineLog.category)
                .all()
            )
            return {
                "total_redlines": total,
                "by_category": {cat: cnt for cat, cnt in by_category},
            }
        finally:
            if close_db:
                db.close()


class FeedbackRepository:
    """用户反馈仓库"""

    @staticmethod
    def create(task_id: str, feedback_type: str, comment: Optional[str] = None, db: Optional[Session] = None) -> Feedback:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            fb = Feedback(
                task_id=task_id,
                feedback_type=feedback_type,
                comment=comment,
            )
            db.add(fb)
            db.commit()
            db.refresh(fb)
            return fb
        finally:
            if close_db:
                db.close()


class FailureRepository:
    """失败记录仓库"""

    @staticmethod
    def create(
        task_id: str,
        failure_type: str,
        step_index: Optional[int] = None,
        fingerprint_hash: Optional[str] = None,
        llm_snapshot: Optional[str] = None,
        error_detail: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Failure:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            f = Failure(
                task_id=task_id,
                failure_type=failure_type,
                step_index=step_index,
                fingerprint_hash=fingerprint_hash,
                llm_snapshot=llm_snapshot,
                error_detail=error_detail,
            )
            db.add(f)
            db.commit()
            db.refresh(f)
            return f
        finally:
            if close_db:
                db.close()


class ConfigRepository:
    """系统配置仓库"""

    @staticmethod
    def get_all(db: Optional[Session] = None) -> dict:
        """获取全部配置"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            configs = db.query(SystemConfig).all()
            return {c.config_key: c.config_value for c in configs}
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get(key: str, db: Optional[Session] = None) -> Optional[dict]:
        """获取单个配置"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
            return config.config_value if config else None
        finally:
            if close_db:
                db.close()

    @staticmethod
    def set(key: str, value: dict, description: Optional[str] = None, db: Optional[Session] = None) -> SystemConfig:
        """设置或更新配置"""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
            if config:
                config.config_value = value
                config.updated_at = datetime.now(timezone.utc)
                if description:
                    config.description = description
            else:
                config = SystemConfig(
                    config_key=key,
                    config_value=value,
                    description=description,
                )
                db.add(config)
            db.commit()
            db.refresh(config)
            return config
        finally:
            if close_db:
                db.close()
