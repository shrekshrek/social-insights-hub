"""Base abstractions for crawler platform adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.tasks import models, service
from src.resources.models import CrawlerAccount, CrawlerProxy


@dataclass
class TaskExecutionContext:
    """Context object provided to platform adapters."""

    db: AsyncSession
    task: models.CrawlerTask
    logger: logging.Logger
    account: CrawlerAccount | None = None
    proxy: CrawlerProxy | None = None

    async def update_progress(
        self,
        progress: int,
        crawled_count: int,
        checkpoint_id: str | None = None,
        checkpoint_data: Dict[str, Any] | None = None,
    ) -> None:
        await service.update_task_progress(
            self.db,
            self.task.id,
            progress=progress,
            crawled_count=crawled_count,
            checkpoint_id=checkpoint_id,
            checkpoint_data=checkpoint_data,
        )

    async def log(
        self, level: str, message: str, detail: Dict[str, Any] | None = None
    ) -> None:
        await service.add_task_log(
            self.db,
            self.task.id,
            level=level,
            message=message,
            detail=detail,
        )
        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(message)


class CrawlerAdapter(ABC):
    """Base class for platform-specific crawler execution."""

    name: str = "unknown"

    @abstractmethod
    async def execute(self, context: TaskExecutionContext) -> None:
        """Execute the crawler with the supplied context."""

    async def pause(
        self, context: TaskExecutionContext
    ) -> None:  # pragma: no cover - optional
        context.logger.debug("Pause requested but not implemented for %s", self.name)

    async def stop(
        self, context: TaskExecutionContext
    ) -> None:  # pragma: no cover - optional
        context.logger.debug("Stop requested but not implemented for %s", self.name)
