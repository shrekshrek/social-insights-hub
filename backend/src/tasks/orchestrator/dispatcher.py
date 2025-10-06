"""Task dispatcher orchestrates execution lifecycle actions."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from src.tasks import models

from .queue import CeleryTaskQueue, TaskQueue
from .validator import TaskValidationError, TaskValidator


class TaskDispatcher:
    """High-level orchestration entry point."""

    def __init__(self, validator: TaskValidator, queue: TaskQueue) -> None:
        self._validator = validator
        self._queue = queue

    async def start_task(self, task: models.CrawlerTask) -> Optional[str]:
        """Validate and schedule a task for execution."""

        self._validator.ensure_startable(task)
        payload: dict[str, Any] = {
            "config": task.config or {},
            "platform": task.platform,
            "crawler_type": task.crawler_type,
        }
        job_id = self._queue.enqueue_start(task.id, payload)
        return job_id

    async def pause_task(self, task: models.CrawlerTask) -> None:
        self._validator.ensure_can_pause(task)
        self._queue.enqueue_pause(task.id)

    async def stop_task(self, task: models.CrawlerTask) -> None:
        self._validator.ensure_can_stop(task)
        self._queue.enqueue_stop(task.id)


@lru_cache(maxsize=1)
def get_task_dispatcher() -> TaskDispatcher:
    return TaskDispatcher(TaskValidator(), CeleryTaskQueue())


__all__ = ["TaskDispatcher", "get_task_dispatcher", "TaskValidationError"]
