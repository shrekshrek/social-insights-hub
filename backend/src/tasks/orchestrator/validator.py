"""Validation helpers for task orchestration."""

from __future__ import annotations

from src.tasks import models


class TaskValidationError(ValueError):
    """Raised when a task fails orchestration validation."""


class TaskValidator:
    """Performs light-weight validation before任务入队."""

    def ensure_startable(self, task: models.CrawlerTask) -> None:
        """Validate start preconditions."""

        if task.config is not None and not isinstance(task.config, dict):
            raise TaskValidationError("任务配置必须是 JSON 对象")

        # Additional platform-specific checks can be added随后。

    def ensure_can_pause(self, task: models.CrawlerTask) -> None:
        if task.status != models.TaskStatus.RUNNING:
            raise TaskValidationError("只有运行中的任务才能暂停")

    def ensure_can_stop(self, task: models.CrawlerTask) -> None:
        if task.status not in (models.TaskStatus.RUNNING, models.TaskStatus.PAUSED):
            raise TaskValidationError("只有运行或暂停中的任务才能停止")
