"""Agent 后台任务

- reset_timed_out_tasks: 定时检测超时的 accepted 任务并重置为 pending
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from src.config import settings
from src.database import AsyncSessionLocal
from src.social_media.tasks.models import DataTask

logger = logging.getLogger(__name__)


async def reset_timed_out_tasks() -> int:
    """将超时的 accepted 任务重置为 pending

    任务被爬虫接收（accepted）后，若超过 AGENT_TASK_TIMEOUT_HOURS 仍未完成，
    说明爬虫崩溃/重启导致任务丢失，重置为 pending 以��重新分配。

    Returns:
        int: 重置的任务数量
    """
    timeout_hours = settings.AGENT_TASK_TIMEOUT_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(DataTask.id, DataTask.keywords, DataTask.accepted_at)
            .where(
                DataTask.status == "accepted",
                DataTask.accepted_at.isnot(None),
                DataTask.accepted_at < cutoff,
                DataTask.is_deleted.is_(False),
            )
        )
        result = await db.execute(stmt)
        timed_out = result.all()

        if not timed_out:
            return 0

        task_ids = [row.id for row in timed_out]

        await db.execute(
            update(DataTask)
            .where(DataTask.id.in_(task_ids))
            .values(status="pending", accepted_at=None, accepted_by=None)
        )
        await db.commit()

        for row in timed_out:
            logger.warning(
                "Task %d (keywords=%r) reset to pending after %.1fh (accepted_at=%s)",
                row.id,
                row.keywords,
                (datetime.now(timezone.utc) - row.accepted_at).total_seconds() / 3600,
                row.accepted_at,
            )

        logger.info("Reset %d timed-out tasks to pending", len(task_ids))
        return len(task_ids)


async def run_periodic_reset(interval_seconds: int = 300) -> None:
    """在 FastAPI lifespan 中运行的周期性重置循环"""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await reset_timed_out_tasks()
        except Exception as e:
            logger.error("reset_timed_out_tasks failed: %s", e, exc_info=True)
