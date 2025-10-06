"""Celery worker tasks for crawler job execution."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict

from src.celery_app import celery_app
from src.database import AsyncSessionLocal
from src.platforms import get_adapter_for_platform
from src.platforms.base import TaskExecutionContext
from src.resources import service as resource_service
from src.resources.models import CrawlerAccount, CrawlerProxy
from src.tasks import models, service

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.execute_task")
def execute_task(task_id: int, payload: Dict[str, Any] | None = None) -> str:
    """Celery entry point executing a crawler任务."""

    async def _run() -> str:
        async with AsyncSessionLocal() as session:
            task: models.CrawlerTask | None = await service.get_task(session, task_id)
            if not task:
                logger.error("任务 %s 不存在", task_id)
                return "missing"

            success = True
            try:
                adapter = get_adapter_for_platform(task.platform)
            except ValueError as exc:
                await service.mark_task_completed(
                    session, task_id, success=False, error=str(exc)
                )
                logger.exception("未找到平台适配器", exc_info=exc)
                return "adapter-missing"

            account: CrawlerAccount | None = None
            proxy: CrawlerProxy | None = None
            try:
                account = await resource_service.allocate_account(
                    session, task.platform, task.id
                )
                proxy = await resource_service.allocate_proxy(session, task.id)

                context = TaskExecutionContext(
                    session,
                    task,
                    logger,
                    account=account,
                    proxy=proxy,
                )

                if account:
                    await context.log("INFO", f"已分配账号 {account.account_name}")
                else:
                    await context.log("WARNING", "未找到可用账号，将尝试匿名执行")

                if proxy:
                    await context.log("INFO", f"已分配代理 {proxy.display_host}")
                else:
                    await context.log("WARNING", "未分配代理，将使用直连")

                await adapter.execute(context)
                await service.mark_task_completed(session, task_id, success=True)
                return "completed"
            except Exception as exc:  # pragma: no cover - runtime failure
                logger.exception("任务执行失败", exc_info=exc)
                await service.mark_task_completed(
                    session, task_id, success=False, error=str(exc)
                )
                success = False
                return "failed"
            finally:
                if account:
                    await resource_service.release_account(
                        session, account.id, success=success
                    )
                if proxy:
                    await resource_service.release_proxy(
                        session, proxy.id, success=success
                    )

    return asyncio.run(_run())
