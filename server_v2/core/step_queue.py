"""
Async FIFO step queue with pause/resume/abort support.

Python equivalent of OpenGuider's core/step-queue.js.

Processes steps sequentially, one at a time. Supports pausing
(finishes current step, stops before next) and aborting.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AsyncStepQueue:
    """Async FIFO queue with pause/resume/abort control.

    Maps to OpenGuider's core/step-queue.js StepQueue.

    Usage:
        queue = AsyncStepQueue(processor=my_processor)
        queue.enqueue(step1)
        queue.enqueue(step2)
        await queue.drain()
    """

    def __init__(self, processor: Optional[Callable] = None):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        self._paused = False
        self._aborted = False
        self._processor = processor or self._default_processor
        self._process_task: Optional[asyncio.Task] = None

        # Events
        self.on_step_started: Optional[Callable] = None
        self.on_step_completed: Optional[Callable] = None
        self.on_drained: Optional[Callable] = None
        self.on_step_error: Optional[Callable] = None

    # ── Queue operations ────────────────────────────────────────────────────

    def enqueue(self, step: Any) -> None:
        """Add a step to the queue."""
        self._queue.put_nowait(step)
        logger.debug(f"Step enqueued, size={self._queue.qsize()}")
        # Start processing if not already
        if not self._processing and not self._aborted:
            self._process_task = asyncio.create_task(self._process_all())

    async def _process_all(self) -> None:
        """Process all enqueued steps."""
        self._processing = True
        try:
            while not self._aborted:
                # Check pause
                if self._paused:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    step = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                await self._process_one(step)
                self._queue.task_done()

            # All done
            if self.on_drained:
                try:
                    self.on_drained()
                except Exception as e:
                    logger.error(f"on_drained callback error: {e}")

        except asyncio.CancelledError:
            logger.info("Step queue processing cancelled")
        finally:
            self._processing = False

    async def _process_one(self, step: Any) -> None:
        """Process a single step."""
        if self.on_step_started:
            try:
                self.on_step_started(step)
            except Exception as e:
                logger.error(f"on_step_started error: {e}")

        try:
            result = await self._processor(step)

            if self.on_step_completed:
                try:
                    self.on_step_completed(step, result)
                except Exception as e:
                    logger.error(f"on_step_completed error: {e}")

        except Exception as e:
            logger.error(f"Step processing error: {e}")
            if self.on_step_error:
                try:
                    self.on_step_error(step, e)
                except Exception as ex:
                    logger.error(f"on_step_error callback error: {ex}")

    async def _default_processor(self, step: Any) -> Any:
        """Default no-op processor."""
        logger.warning(f"Default processor called for step: {step}")
        return None

    # ── Control ─────────────────────────────────────────────────────────────

    def pause(self) -> None:
        """Pause processing after current step completes."""
        self._paused = True
        logger.info("Step queue paused")

    def resume(self) -> None:
        """Resume processing."""
        self._paused = False
        logger.info("Step queue resumed")
        if not self._processing and not self._aborted:
            self._process_task = asyncio.create_task(self._process_all())

    def abort(self) -> None:
        """Abort all processing."""
        self._aborted = True
        logger.info("Step queue aborted")

    async def drain(self) -> None:
        """Wait for all enqueued steps to complete."""
        if self._process_task and not self._process_task.done():
            await self._process_task
        logger.debug("Step queue drained")

    # ── Status ──────────────────────────────────────────────────────────────

    @property
    def is_processing(self) -> bool:
        return self._processing

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    @property
    def size(self) -> int:
        return self._queue.qsize()
