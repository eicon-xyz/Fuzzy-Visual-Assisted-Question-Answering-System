"""
MemoryExtractor — 从成功/失败任务中自动提取记忆。

任务完成后异步调用，用便宜 LLM 提取结构化结论，
去重后写入 t_memories，同时消解关联的 failure_lesson。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from server.config import settings
from server.database.repository import MemoryRepository
from server.services.llm.providers import extract_json_object
from server.services.memory.deduper import check_and_merge
from server.services.memory.embedder import cosine_similarity, encode, from_blob
from server.services.memory.retriever import get_retriever

logger = logging.getLogger(__name__)

EXTRACTOR_PROMPT = """从以下任务执行记录中提取关键信息。严格返回 JSON，不要任何其他文字：
{"app": "使用的应用名(无则null)", "path": "涉及的文件路径(无则null)", "summary": "一句话概括操作(≤100字)"}

任务: {query}
步骤: {steps}"""

FAILURE_EXTRACTOR_PROMPT = """以下任务执行失败了。提取失败原因。严格返回 JSON，不要任何其他文字：
{"reason": "失败原因(≤100字)", "step_that_failed": "失败的步骤描述"}

任务: {query}
步骤: {steps}
错误: {error}"""


class MemoryExtractor:
    """Extracts memories from completed/failed tasks using a cheap LLM."""

    def __init__(self):
        self._retriever = get_retriever()

    # ── Public API ────────────────────────────────────────────────────

    def extract_from_success(
        self,
        user_id: str,
        user_query: str,
        steps: list[dict],
    ) -> None:
        """Called after a task succeeds. Extracts success_pattern memory."""
        try:
            result = self._extract_with_llm(user_query, steps, is_failure=False)
        except Exception as e:
            logger.warning("Memory extraction LLM call failed: %s", e)
            return

        summary = result.get("summary", user_query[:100])
        app = result.get("app")
        path = result.get("path")

        # Build enriched summary
        enriched = summary
        if app:
            enriched = f"[{app}] {enriched}"
        if path:
            enriched = f"{enriched} (路径: {path})"

        # Determine category
        category = "task_workflow"
        if app and not path:
            category = "app_preference"
        elif path and not app:
            category = "path_habit"

        # Encode for dedup
        vec = encode(user_query)
        if vec is None:
            return

        # Dedup + insert + sync cache
        memory_id = check_and_merge(
            user_id=user_id,
            summary=enriched,
            category=category,
            memory_type="success_pattern",
            trigger_query=user_query,
            embedding=vec,
        )
        if memory_id:
            self._retriever.add_to_cache(
                user_id=user_id,
                memory_id=memory_id,
                memory_type="success_pattern",
                category=category,
                trigger_query=user_query,
                summary=enriched,
                embedding=vec,
            )

        # Resolve related failure lessons
        self._resolve_failure_lessons(user_id, user_query)

        logger.info("Memory extracted from success: %s", enriched[:60])

    def extract_from_failure(
        self,
        user_id: str,
        user_query: str,
        steps: list[dict],
        error_detail: str = "",
    ) -> None:
        """Called only when a task fully fails (agent loop exhausted).

        Creates a failure_lesson memory for future avoidance.
        """
        try:
            result = self._extract_with_llm(
                user_query, steps, is_failure=True, error_detail=error_detail
            )
        except Exception as e:
            logger.warning("Failure memory extraction LLM call failed: %s", e)
            return

        reason = result.get("reason", error_detail[:100] or user_query[:100])
        summary = f"失败: {reason}"

        vec = encode(user_query)
        if vec is None:
            return

        memory_id = check_and_merge(
            user_id=user_id,
            summary=summary,
            category="failure_avoidance",
            memory_type="failure_lesson",
            trigger_query=user_query,
            embedding=vec,
        )
        if memory_id:
            self._retriever.add_to_cache(
                user_id=user_id,
                memory_id=memory_id,
                memory_type="failure_lesson",
                category="failure_avoidance",
                trigger_query=user_query,
                summary=summary,
                embedding=vec,
            )

        logger.info("Failure memory recorded: %s", summary[:60])

    # ── Internal helpers ──────────────────────────────────────────────

    def _extract_with_llm(
        self,
        query: str,
        steps: list[dict],
        is_failure: bool = False,
        error_detail: str = "",
    ) -> dict:
        """Call cheap LLM to extract structured info from task execution."""
        from server.services.llm.providers import call_llm

        # Serialize steps
        steps_text = "\n".join(
            f"{s.get('step_index', i+1)}. {s.get('instruction', str(s))}"
            for i, s in enumerate(steps[:10])  # Max 10 steps to keep prompt small
        )

        if is_failure:
            prompt = FAILURE_EXTRACTOR_PROMPT.format(
                query=query, steps=steps_text, error=error_detail[:200]
            )
        else:
            prompt = EXTRACTOR_PROMPT.format(query=query, steps=steps_text)

        provider = getattr(settings, "MEMORY_EXTRACTOR_PROVIDER", "qwen")
        model = getattr(settings, "MEMORY_EXTRACTOR_MODEL", "qwen-turbo")

        raw = call_llm(
            user_text=prompt,
            images=None,
            system_prompt="You are a task analysis assistant. Always respond with ONLY valid JSON, no markdown, no extra text.",
            provider=provider,
            model=model,
            temperature=0.1,
            max_tokens=256,
            timeout=30,
        )

        # Parse: try extract_json_object first, then raw json.loads
        try:
            return extract_json_object(raw)
        except Exception:
            pass

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Cheap LLM returned non-JSON, using raw text fallback")
            return {
                "app": None,
                "path": None,
                "summary": raw[:100],
            }

    def _resolve_failure_lessons(self, user_id: str, user_query: str) -> None:
        """Check if this success resolves any active failure_lesson memories.

        Only resolves if cosine_similarity > 0.9 (strict threshold).
        """
        query_vec = encode(user_query)
        if query_vec is None:
            return

        failures = MemoryRepository.get_by_user_and_type(
            user_id, "failure_lesson", is_active=True
        )

        for f in failures:
            if f.embedding is None:
                continue
            try:
                f_vec = from_blob(f.embedding)
                sim = cosine_similarity(query_vec, f_vec)
                if sim > 0.9:
                    logger.info(
                        "Resolving failure lesson '%s' (sim=%.3f) via successful task",
                        f.summary[:50],
                        sim,
                    )
                    MemoryRepository.increment_resolved(f.memory_id)
                    # Also remove from cache
                    self._retriever.remove_from_cache(user_id, f.memory_id)
            except Exception as e:
                logger.warning("Failed to compare with failure lesson %s: %s", f.memory_id, e)
                continue
