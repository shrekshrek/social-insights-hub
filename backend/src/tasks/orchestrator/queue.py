"""Queue abstraction for task orchestration."""

from __future__ import annotations

from typing import Any, Protocol

from src.celery_app import celery_app


class TaskQueue(Protocol):
    """Protocol describing a task queue implementation."""

    def enqueue_start(self, task_id: int, payload: dict[str, Any]) -> str:
        """Schedule a task execution and return the queue job ID."""

    def enqueue_pause(self, task_id: int) -> None:
        """Request a running task to pause (best-effort)."""

    def enqueue_stop(self, task_id: int) -> None:
        """Request a running task to stop (best-effort)."""


class CeleryTaskQueue:
    """Celery-backed task queue implementation."""

    def __init__(self) -> None:
        self._celery = celery_app

    def enqueue_start(self, task_id: int, payload: dict[str, Any]) -> str:
        from src.tasks.worker import execute_task

        result = execute_task.apply_async(
            kwargs={"task_id": task_id, "payload": payload}
        )
        return result.id

    def enqueue_pause(self, task_id: int) -> None:  # pragma: no cover - stub
        # TODO: integrate with task execution backend
        return None

    def enqueue_stop(self, task_id: int) -> None:  # pragma: no cover - stub
        # TODO: integrate with task execution backend
        return None
