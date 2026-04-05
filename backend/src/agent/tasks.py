"""Agent 后台任务

- reset_timed_out_tasks: 检测超时的 accepted/running 任务并重置为 pending
  （由 APScheduler 在 FastAPI asyncio 事件循环中直接 await 调用）
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update

from src.config import settings
from src.database import AsyncSessionLocal
from src.social_media.tasks.models import SocialTask

logger = logging.getLogger(__name__)


async def reset_timed_out_tasks() -> int:
    """将超时的 accepted/running 任务重置为 pending。

    两种场景均以 accepted_at 作为计时起点：
    - accepted：爬虫接收后未启动（崩溃/重启）
    - running：爬虫启动后中途崩溃，进度上报随之停止

    Returns:
        int: 重置的任务数量
    """
    timeout_hours = settings.AGENT_TASK_TIMEOUT_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(SocialTask.id, SocialTask.keywords, SocialTask.status, SocialTask.accepted_at)
            .where(
                or_(
                    SocialTask.status == "accepted",
                    SocialTask.status == "running",
                ),
                SocialTask.accepted_at.isnot(None),
                SocialTask.accepted_at < cutoff,
                SocialTask.is_deleted.is_(False),
            )
        )
        timed_out = (await db.execute(stmt)).all()

        if not timed_out:
            return 0

        task_ids = [row.id for row in timed_out]
        await db.execute(
            update(SocialTask)
            .where(SocialTask.id.in_(task_ids))
            .values(status="pending", accepted_at=None, accepted_by=None)
        )
        await db.commit()

    now = datetime.now(timezone.utc)
    for row in timed_out:
        logger.warning(
            "Task %d (keywords=%r, status=%s) reset to pending after %.1fh (accepted_at=%s)",
            row.id,
            row.keywords,
            row.status,
            (now - row.accepted_at).total_seconds() / 3600,
            row.accepted_at,
        )

    logger.info("Reset %d timed-out tasks to pending", len(task_ids))
    return len(task_ids)
