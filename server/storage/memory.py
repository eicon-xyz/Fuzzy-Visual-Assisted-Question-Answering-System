"""
HAJIMI Demo 内存存储层
Demo 阶段用内存 dict 保存任务状态，服务重启后清空
"""
import threading
import uuid
from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel

from server.models.schemas import ProcessResponse, Intent, Blueprint, Step


class TaskState(BaseModel):
    """任务运行时状态"""

    task_id: str
    query: str
    intent: Intent
    blueprint: Blueprint
    steps: list[Step]
    ui_elements: list[dict]
    created_at: str
    updated_at: str
    fingerprint: Optional[str] = None


class TaskStore:
    """线程安全的内存任务存储"""

    def __init__(self):
        self._store: Dict[str, TaskState] = {}
        self._lock = threading.Lock()

    def create(self, response: ProcessResponse, query: str) -> TaskState:
        """根据 process 响应创建任务状态"""
        now = datetime.now().isoformat()
        state = TaskState(
            task_id=response.task_id,
            query=query,
            intent=response.intent,
            blueprint=response.blueprint,
            steps=response.steps,
            ui_elements=[e.model_dump() for e in response.ui_elements],
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._store[state.task_id] = state
        return state

    def get(self, task_id: str) -> Optional[TaskState]:
        """获取任务状态"""
        with self._lock:
            return self._store.get(task_id)

    def update(self, state: TaskState) -> TaskState:
        """更新任务状态"""
        state.updated_at = datetime.now().isoformat()
        with self._lock:
            self._store[state.task_id] = state
        return state

    def delete(self, task_id: str) -> bool:
        """删除任务状态"""
        with self._lock:
            if task_id in self._store:
                del self._store[task_id]
                return True
            return False

    def generate_id(self) -> str:
        """生成任务 ID"""
        return str(uuid.uuid4())


# 全局单例
task_store = TaskStore()
