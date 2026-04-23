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

    活跃度信号：`updated_at`（progress report / status 变更都会通过 SQLAlchemy
    onupdate 自动推进）。用 `updated_at < cutoff` 替代原先的 `accepted_at < cutoff`：

    - **正常跑的长任务**：progress report 持续推进 updated_at → 不会被错杀
      （旧逻辑用 accepted_at，跑满 2h 的大任务会被错杀）
    - **agent 崩溃 / 网络中断**：progress 停止上报 → updated_at 不再推进 → 按 timeout 重置
    - **爬虫端平台暂停超过 timeout**：updated_at 同样停滞 → 会被重置为 pending。
      配合 upload_result 白名单对 pending 状态的兜底（带告警），暂停恢复后仍能上传

    Returns:
        int: 重置的任务数量
    """
    timeout_hours = settings.AGENT_TASK_TIMEOUT_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(SocialTask.id, SocialTask.keywords, SocialTask.status,
                   SocialTask.accepted_at, SocialTask.updated_at)
            .where(
                or_(
                    SocialTask.status == "accepted",
                    SocialTask.status == "running",
                ),
                SocialTask.updated_at < cutoff,
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
        ref_time = row.updated_at
        hours_stuck = (now - ref_time).total_seconds() / 3600 if ref_time else 0
        logger.warning(
            "Task %d (keywords=%r, status=%s) reset to pending after %.1fh idle (updated_at=%s)",
            row.id, row.keywords, row.status, hours_stuck, row.updated_at,
        )

    logger.info("Reset %d timed-out tasks to pending", len(task_ids))
    return len(task_ids)
