"""
爬虫任务业务逻辑
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.pagination import PaginationParams, paginate_query

from . import models, schemas
from .orchestrator import get_task_dispatcher
from .orchestrator.validator import TaskValidationError

logger = logging.getLogger(__name__)

dispatcher = get_task_dispatcher()


# ============================================================================
# 任务管理
# ============================================================================


async def create_task(
    db: AsyncSession, task_data: schemas.CrawlerTaskCreate, user_id: int
) -> models.CrawlerTask:
    """创建爬虫任务"""
    task = models.CrawlerTask(
        name=task_data.name,
        platform=task_data.platform,
        crawler_type=task_data.crawler_type,
        config=task_data.config,
        status=models.TaskStatus.PENDING,
        created_by=user_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 记录创建日志
    await add_task_log(
        db,
        task.id,
        "INFO",
        f"任务创建成功: {task.name} ({task.platform}/{task.crawler_type})",
    )

    logger.info(f"创建爬虫任务: {task.id} - {task.name}")
    return task


async def get_task(db: AsyncSession, task_id: int) -> Optional[models.CrawlerTask]:
    """获取任务基本信息（不含日志）"""
    result = await db.execute(
        select(models.CrawlerTask).where(models.CrawlerTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_task_with_logs(
    db: AsyncSession, task_id: int
) -> Optional[models.CrawlerTask]:
    """获取任务详情（含日志）"""
    result = await db.execute(
        select(models.CrawlerTask)
        .options(selectinload(models.CrawlerTask.logs))
        .where(models.CrawlerTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    pagination: PaginationParams,
    platform: Optional[models.PlatformType] = None,
    status: Optional[models.TaskStatus] = None,
    created_by: Optional[int] = None,
) -> tuple[list[models.CrawlerTask], int]:
    """获取任务列表(分页)"""
    # 构建查询条件
    conditions = []
    if platform:
        conditions.append(models.CrawlerTask.platform == platform)
    if status:
        conditions.append(models.CrawlerTask.status == status)
    if created_by:
        conditions.append(models.CrawlerTask.created_by == created_by)

    # 查询
    query = select(models.CrawlerTask).where(and_(*conditions) if conditions else True)
    query = query.order_by(desc(models.CrawlerTask.created_at))

    return await paginate_query(db, query, pagination)


async def update_task(
    db: AsyncSession, task_id: int, update_data: schemas.CrawlerTaskUpdate
) -> Optional[models.CrawlerTask]:
    """更新任务"""
    task = await get_task(db, task_id)
    if not task:
        return None

    # 更新字段
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)

    logger.info(f"更新任务: {task_id}")
    return task


async def delete_task(db: AsyncSession, task_id: int) -> bool:
    """删除任务"""
    task = await get_task(db, task_id)
    if not task:
        return False

    # 只能删除未运行的任务
    if task.status == models.TaskStatus.RUNNING:
        raise ValueError("无法删除正在运行的任务，请先停止任务")

    await db.delete(task)
    await db.commit()

    logger.info(f"删除任务: {task_id}")
    return True


# ============================================================================
# 任务控制
# ============================================================================


async def start_task(db: AsyncSession, task_id: int) -> models.CrawlerTask:
    """启动任务"""
    task = await get_task(db, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    if task.status not in [models.TaskStatus.PENDING, models.TaskStatus.PAUSED]:
        raise ValueError(f"任务状态错误，无法启动: {task.status}")

    task.status = models.TaskStatus.RUNNING
    task.started_at = datetime.utcnow()
    task.error_message = None

    await db.commit()
    await db.refresh(task)

    await add_task_log(db, task_id, "INFO", "任务开始执行")
    logger.info(f"启动任务: {task_id}")

    try:
        job_id = await dispatcher.start_task(task)
    except TaskValidationError as exc:
        task.status = models.TaskStatus.FAILED
        task.error_message = str(exc)
        await db.commit()
        await db.refresh(task)
        await add_task_log(
            db,
            task_id,
            "ERROR",
            f"任务校验失败: {exc}",
        )
        logger.exception("任务调度校验失败", exc_info=exc)
        raise ValueError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure
        task.status = models.TaskStatus.FAILED
        task.error_message = str(exc)
        await db.commit()
        await db.refresh(task)
        await add_task_log(
            db,
            task_id,
            "ERROR",
            "任务调度失败",
            detail={"error": repr(exc)},
        )
        logger.exception("任务调度异常", exc_info=exc)
        raise ValueError("任务调度失败，请稍后再试") from exc
    else:
        if job_id:
            await add_task_log(
                db,
                task_id,
                "INFO",
                f"任务已提交至队列，作业ID: {job_id}",
            )

    return task


async def pause_task(db: AsyncSession, task_id: int) -> models.CrawlerTask:
    """暂停任务"""
    task = await get_task(db, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    try:
        await dispatcher.pause_task(task)
    except TaskValidationError as exc:
        raise ValueError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure
        logger.exception("任务暂停调度失败", exc_info=exc)
        raise ValueError("任务暂停调度失败") from exc

    task.status = models.TaskStatus.PAUSED
    await db.commit()
    await db.refresh(task)

    await add_task_log(db, task_id, "INFO", "任务已暂停")
    logger.info(f"暂停任务: {task_id}")

    return task


async def stop_task(db: AsyncSession, task_id: int) -> models.CrawlerTask:
    """停止任务"""
    task = await get_task(db, task_id)
    if not task:
        raise ValueError(f"任务不存在: {task_id}")

    try:
        await dispatcher.stop_task(task)
    except TaskValidationError as exc:
        raise ValueError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("任务停止调度失败", exc_info=exc)
        raise ValueError("任务停止调度失败") from exc

    task.status = models.TaskStatus.CANCELLED
    task.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)

    await add_task_log(db, task_id, "WARNING", "任务已停止")
    logger.info(f"停止任务: {task_id}")

    return task


async def update_task_progress(
    db: AsyncSession,
    task_id: int,
    progress: int,
    crawled_count: int,
    checkpoint_id: Optional[str] = None,
    checkpoint_data: Optional[dict] = None,
) -> None:
    """更新任务进度"""
    task = await get_task(db, task_id)
    if not task:
        return

    task.progress = progress
    task.crawled_count = crawled_count
    if checkpoint_id:
        task.checkpoint_id = checkpoint_id
    if checkpoint_data:
        task.checkpoint_data = checkpoint_data

    await db.commit()


async def mark_task_completed(
    db: AsyncSession, task_id: int, success: bool = True, error: Optional[str] = None
) -> None:
    """标记任务完成"""
    task = await get_task(db, task_id)
    if not task:
        return

    task.status = models.TaskStatus.COMPLETED if success else models.TaskStatus.FAILED
    task.completed_at = datetime.utcnow()
    task.progress = 100 if success else task.progress
    if error:
        task.error_message = error

    await db.commit()

    log_level = "INFO" if success else "ERROR"
    log_message = "任务完成" if success else f"任务失败: {error}"
    await add_task_log(db, task_id, log_level, log_message)

    logger.info(f"任务完成: {task_id}, 成功={success}")


# ============================================================================
# 任务日志
# ============================================================================


async def add_task_log(
    db: AsyncSession,
    task_id: int,
    level: str,
    message: str,
    detail: Optional[dict] = None,
) -> models.TaskLog:
    """添加任务日志"""
    log = models.TaskLog(task_id=task_id, level=level, message=message, detail=detail)
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_task_logs(
    db: AsyncSession, task_id: int, limit: int = 100
) -> list[models.TaskLog]:
    """获取任务日志"""
    result = await db.execute(
        select(models.TaskLog)
        .where(models.TaskLog.task_id == task_id)
        .order_by(desc(models.TaskLog.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


# ============================================================================
# 统计
# ============================================================================


async def get_task_statistics(db: AsyncSession) -> schemas.TaskStatistics:
    """获取任务统计"""
    result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((models.CrawlerTask.status == "pending", 1), else_=0)).label(
                "pending"
            ),
            func.sum(case((models.CrawlerTask.status == "running", 1), else_=0)).label(
                "running"
            ),
            func.sum(
                case((models.CrawlerTask.status == "completed", 1), else_=0)
            ).label("completed"),
            func.sum(case((models.CrawlerTask.status == "failed", 1), else_=0)).label(
                "failed"
            ),
            func.sum(
                case((models.CrawlerTask.status == "cancelled", 1), else_=0)
            ).label("cancelled"),
        )
    )

    row = result.one()
    return schemas.TaskStatistics(
        total=row.total or 0,
        pending=row.pending or 0,
        running=row.running or 0,
        completed=row.completed or 0,
        failed=row.failed or 0,
        cancelled=row.cancelled or 0,
    )
