"""Agent 定时任务

- reset_timed_out_tasks: 定时检测超时的 accepted 任务并重置为 pending
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from src.celery_app import celery_app
from src.config import settings
from src.database import SyncSessionLocal
from src.social_media.tasks.models import DataTask

logger = logging.getLogger(__name__)


@celery_app.task(
    name="agent.reset_timed_out_tasks",
    bind=True,
    max_retries=0,
)
def reset_timed_out_tasks(self) -> dict:
    """将超时的 accepted 任务重置为 pending

    任务被爬虫接收（accepted）后，若超过 AGENT_TASK_TIMEOUT_HOURS 仍未完成，
    说明爬虫崩溃/重启导致任务丢失，重置为 pending 以供重新分配。
    """
    timeout_hours = settings.AGENT_TASK_TIMEOUT_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

    with SyncSessionLocal() as db:
        # 查询超时任务
        stmt = (
            select(DataTask.id, DataTask.keywords, DataTask.accepted_at)
            .where(
                DataTask.status == "accepted",
                DataTask.accepted_at.isnot(None),
                DataTask.accepted_at < cutoff,
                DataTask.is_deleted.is_(False),
            )
        )
        result = db.execute(stmt)
        timed_out = result.all()

        if not timed_out:
            return {"reset_count": 0}

        task_ids = [row.id for row in timed_out]

        # 批量重置
        db.execute(
            update(DataTask)
            .where(DataTask.id.in_(task_ids))
            .values(status="pending", accepted_at=None, accepted_by=None)
        )
        db.commit()

        for row in timed_out:
            logger.warning(
                "Task %d (keywords=%r) reset to pending after %.1fh (accepted_at=%s)",
                row.id,
                row.keywords,
                (datetime.now(timezone.utc) - row.accepted_at).total_seconds() / 3600,
                row.accepted_at,
            )

        logger.info("Reset %d timed-out tasks to pending", len(task_ids))
        return {"reset_count": len(task_ids), "task_ids": task_ids}
