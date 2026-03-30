"""Agent 后台任务（Celery/Beat 调度）

- reset_timed_out_tasks_sync: 检测超时 accepted 任务并重置为 pending
- reset_timed_out_tasks_task: 提供给 Celery Beat 的定时入口
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.config import settings
from src.database import SyncSessionLocal
from src.social_media.tasks.models import DataTask

logger = logging.getLogger(__name__)


def reset_timed_out_tasks_sync() -> int:
    """将超时的 accepted 任务重置为 pending。

    任务被爬虫接收（accepted）后，若超过 AGENT_TASK_TIMEOUT_HOURS 仍未完成，
    说明爬虫崩溃/重启导致任务丢失，重置为 pending 以便重新分配。

    Returns:
        int: 重置的任务数量
    """
    timeout_hours = settings.AGENT_TASK_TIMEOUT_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

    with SyncSessionLocal() as db:
        stmt = (
            select(DataTask.id, DataTask.keywords, DataTask.accepted_at)
            .where(
                DataTask.status == "accepted",
                DataTask.accepted_at.isnot(None),
                DataTask.accepted_at < cutoff,
                DataTask.is_deleted.is_(False),
            )
        )
        timed_out = db.execute(stmt).all()

        if not timed_out:
            return 0

        task_ids = [row.id for row in timed_out]
        db.execute(
            update(DataTask)
            .where(DataTask.id.in_(task_ids))
            .values(status="pending", accepted_at=None, accepted_by=None)
        )
        db.commit()

        now = datetime.now(timezone.utc)
        for row in timed_out:
            logger.warning(
                "Task %d (keywords=%r) reset to pending after %.1fh (accepted_at=%s)",
                row.id,
                row.keywords,
                (now - row.accepted_at).total_seconds() / 3600,
                row.accepted_at,
            )

        logger.info("Reset %d timed-out tasks to pending", len(task_ids))
        return len(task_ids)


@celery_app.task(name="agent.reset_timed_out_tasks", bind=True, max_retries=0)
def reset_timed_out_tasks_task(self) -> dict[str, int]:
    """Celery Beat 触发：执行超时任务回收。"""
    reset_count = reset_timed_out_tasks_sync()
    logger.info("Agent timeout reset completed, reset_count=%d", reset_count)
    return {"reset_count": reset_count}
