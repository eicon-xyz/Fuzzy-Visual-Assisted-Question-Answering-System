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

EXTRACTOR_PROMPT = """你是一个任务分析助手。从任务记录中提取结构化信息。
只输出一个JSON对象，不要任何其他文字或代码块标记。

输出格式:
{{"app": "使用的应用名(如Chrome/WPS/QQ音乐)，无则填null", "path": "涉及的文件夹路径，无则填null", "summary": "一句话概括操作(≤20字)"}}

任务: {query}
步骤: {steps}"""


FAILURE_EXTRACTOR_PROMPT = """以下任务执行失败了。提取失败原因。
只输出一个JSON对象，不要任何其他文字或代码块标记。

{{"reason": "失败原因(≤20字)", "step_that_failed": "失败的步骤描述"}}

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
            logger.warning("Memory extraction LLM call failed: %s; storing fallback memory", e)
            # Fallback: store memory with raw query as summary
            self._insert_without_embedding(
                user_id=user_id,
                memory_type="success_pattern",
                category="task_workflow",
                trigger_query=user_query,
                summary=user_query[:500],
            )
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
            logger.warning("Embedding model unavailable — storing without embedding")
            # Store without embedding — retrieval won't match by similarity,
            # but the memory is still persisted for diagnostic purposes
            vec = None

        # Dedup + insert + sync cache
        if vec is not None:
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
        else:
            # No embedding — store without embedding blob, skip cache
            logger.info("Storing memory without embedding (model unavailable)")
            self._insert_without_embedding(
                user_id=user_id,
                memory_type="success_pattern",
                category=category,
                trigger_query=user_query,
                summary=enriched,
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
            # Fallback: store bare failure memory
            self._insert_without_embedding(
                user_id=user_id,
                memory_type="failure_lesson",
                category="failure_avoidance",
                trigger_query=user_query,
                summary=f"失败: {error_detail[:200] or user_query[:200]}",
            )
            return

        reason = result.get("reason", error_detail[:100] or user_query[:100])
        summary = f"失败: {reason}"

        vec = encode(user_query)
        if vec is not None:
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
        else:
            logger.info("Storing failure memory without embedding (model unavailable)")
            self._insert_without_embedding(
                user_id=user_id,
                memory_type="failure_lesson",
                category="failure_avoidance",
                trigger_query=user_query,
                summary=summary,
            )

        logger.info("Failure memory recorded: %s", summary[:60])

    # ── Internal helpers ──────────────────────────────────────────────

    def _insert_without_embedding(
        self,
        user_id: str,
        memory_type: str,
        category: Optional[str],
        trigger_query: str,
        summary: str,
    ) -> Optional[str]:
        """Insert a memory row WITHOUT embedding blob (model unavailable fallback)."""
        try:
            mem = MemoryRepository.create(
                user_id=user_id,
                memory_type=memory_type,
                trigger_query=trigger_query,
                summary=summary[:500],
                embedding_bytes=None,
                category=category,
            )
            logger.info("Memory stored without embedding: %s (id=%s)", summary[:50], mem.memory_id)
            return mem.memory_id
        except Exception as e:
            logger.error("Failed to insert memory without embedding: %s", e)
            return None

    def _extract_with_llm(
        self,
        query: str,
        steps: list[dict],
        is_failure: bool = False,
        error_detail: str = "",
    ) -> dict:
        """Call LLM to extract structured info from task execution."""
        from server.services.llm.providers import call_llm as _llm_call

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

        # Use memory-specific config if set, otherwise fall back to main LLM
        provider = getattr(settings, "MEMORY_EXTRACTOR_PROVIDER", None) or settings.LLM_PROVIDER
        model = getattr(settings, "MEMORY_EXTRACTOR_MODEL", None) or settings.LLM_MODEL

        raw = _llm_call(
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
            parsed = extract_json_object(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            # json.loads succeeded but returned a non-dict (e.g. bare string)
            # Treat as parse failure and fall through
        except (json.JSONDecodeError, TypeError):
            pass

        # Final fallback: use raw text
        logger.warning("LLM returned non-JSON (%s...), using raw text fallback", raw[:50])
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
