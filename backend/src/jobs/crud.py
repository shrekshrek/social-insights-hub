"""AnalysisJob CRUD 操作

提供 AnalysisJob 的查询、更新、删除等操作。跨渠道共用。
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from src.jobs.models import AnalysisJob
from src.jobs.schemas import AnalysisProgressResponse


async def _get_job_or_404(db: AsyncSession, job_id: int) -> AnalysisJob:
    """查询 AnalysisJob，不存在则抛 404。"""
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found",
        )
    return job


async def set_celery_task_id(
    db: AsyncSession, job_id: int, celery_task_id: str
) -> None:
    """把真实的 celery task id 回填到 AnalysisJob（取代占位的 pending- 前缀）。"""
    job = await _get_job_or_404(db, job_id)
    job.celery_task_id = celery_task_id
    await db.flush()


async def get_analysis_jobs(
    db: AsyncSession,
    current_user_id: int,
    page: int = 1,
    page_size: int = 20,
    social_monitor_id: int | None = None,
    social_task_id: int | None = None,
    news_monitor_id: int | None = None,
    news_task_id: int | None = None,
    analysis_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[List[Dict[str, Any]], int]:
    """获取全局分析任务列表（带筛选和关联信息）"""
    from src.social_media.monitors.models import SocialMonitor as SocialMonitor
    from src.social_media.tasks.models import SocialTask as SocialTask
    from src.news_media.monitors.models import NewsMonitor
    from src.news_media.tasks.models import NewsTask
    from src.auth.models import User
    # NOTE: SocialSlice 仍住在 src.social_media.analysis.models（社媒专属，P3 会迁往 social_media/analysis/）
    # 这里 lazy import 是为了避免 jobs → analysis 的顶层循环依赖。
    from src.social_media.analysis.models import SocialSlice

    # 构建基础查询（全部用 outer join，因为各 FK 均为 nullable）
    stmt = (
        select(
            AnalysisJob,
            SocialMonitor.name.label("social_monitor_name"),
            SocialTask.name.label("social_task_name"),
            NewsMonitor.name.label("news_monitor_name"),
            NewsTask.name.label("news_task_name"),
            User.username.label("user_name"),
        )
        .join(SocialMonitor, AnalysisJob.social_monitor_id == SocialMonitor.id, isouter=True)
        .join(SocialTask, AnalysisJob.social_task_id == SocialTask.id, isouter=True)
        .join(NewsMonitor, AnalysisJob.news_monitor_id == NewsMonitor.id, isouter=True)
        .join(NewsTask, AnalysisJob.news_task_id == NewsTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
    )

    # 筛选条件
    conditions = []

    if social_monitor_id is not None:
        conditions.append(AnalysisJob.social_monitor_id == social_monitor_id)

    if social_task_id is not None:
        conditions.append(AnalysisJob.social_task_id == social_task_id)

    if news_monitor_id is not None:
        conditions.append(AnalysisJob.news_monitor_id == news_monitor_id)

    if news_task_id is not None:
        conditions.append(AnalysisJob.news_task_id == news_task_id)

    if analysis_type:
        conditions.append(AnalysisJob.analysis_type == analysis_type)

    if status:
        conditions.append(AnalysisJob.status == status)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            conditions.append(AnalysisJob.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            # 结束日期包含当天
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            conditions.append(AnalysisJob.created_at <= end_dt)
        except ValueError:
            pass

    if conditions:
        stmt = stmt.where(and_(*conditions))

    # 计算总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    # 分页查询
    stmt = stmt.order_by(AnalysisJob.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    rows = result.all()

    # ===== 批量补齐切片信息（用于项目级切片相关的 AnalysisJob 展示）=====
    slice_ids: set[int] = set()
    for row in rows:
        job = row.AnalysisJob
        cfg = job.analysis_config if isinstance(job.analysis_config, dict) else {}
        sid = cfg.get("slice_id")
        if job.social_task_id is None and isinstance(sid, int):
            slice_ids.add(sid)

    slice_name_by_id: dict[int, str | None] = {}
    if slice_ids:
        snap_stmt = select(
            SocialSlice.id, SocialSlice.name
        ).where(SocialSlice.id.in_(list(slice_ids)))
        snap_rows = (await db.execute(snap_stmt)).all()
        slice_name_by_id = {int(r[0]): r[1] for r in snap_rows}

    # 转换为字典列表（包含关联名称）
    items = []
    for row in rows:
        job = row.AnalysisJob
        cfg = job.analysis_config if isinstance(job.analysis_config, dict) else {}
        slice_id = cfg.get("slice_id") if job.social_task_id is None else None
        if not isinstance(slice_id, int):
            slice_id = None
        item = {
            "id": job.id,
            "social_monitor_id": job.social_monitor_id,
            "social_task_id": job.social_task_id,
            "news_monitor_id": job.news_monitor_id,
            "news_task_id": job.news_task_id,
            "user_id": job.user_id,
            "analysis_type": job.analysis_type,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "analysis_config": job.analysis_config,
            "source_task_ids": job.source_task_ids,
            "source_count": job.source_count,
            "analyzed_count": job.analyzed_count,
            "failed_count": job.failed_count,
            "result_data": job.result_data,
            "analysis_summary": job.analysis_summary,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "processing_time": job.processing_time,
            "token_usage": job.token_usage,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            # 关联名称
            "social_monitor_name": row.social_monitor_name,
            "social_task_name": row.social_task_name,
            "news_monitor_name": row.news_monitor_name,
            "news_task_name": row.news_task_name,
            "slice_id": slice_id,
            "slice_name": slice_name_by_id.get(slice_id)
            if slice_id is not None
            else None,
            "user_name": row.user_name,
        }
        items.append(item)

    return items, total


async def get_analysis_job(
    db: AsyncSession, job_id: int, current_user_id: int
) -> Optional[Dict[str, Any]]:
    """获取单个分析任务详情（带关联信息）"""
    from src.social_media.monitors.models import SocialMonitor as SocialMonitor
    from src.social_media.tasks.models import SocialTask as SocialTask
    from src.news_media.monitors.models import NewsMonitor
    from src.news_media.tasks.models import NewsTask
    from src.auth.models import User

    stmt = (
        select(
            AnalysisJob,
            SocialMonitor.name.label("social_monitor_name"),
            SocialTask.name.label("social_task_name"),
            NewsMonitor.name.label("news_monitor_name"),
            NewsTask.name.label("news_task_name"),
            User.username.label("user_name"),
        )
        .join(SocialMonitor, AnalysisJob.social_monitor_id == SocialMonitor.id, isouter=True)
        .join(SocialTask, AnalysisJob.social_task_id == SocialTask.id, isouter=True)
        .join(NewsMonitor, AnalysisJob.news_monitor_id == NewsMonitor.id, isouter=True)
        .join(NewsTask, AnalysisJob.news_task_id == NewsTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
        .where(AnalysisJob.id == job_id)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return None

    job = row.AnalysisJob

    # 验证用户权限（按模块判断）
    await _assert_job_access(db, job, current_user_id)

    return {
        "id": job.id,
        "social_monitor_id": job.social_monitor_id,
        "social_task_id": job.social_task_id,
        "news_monitor_id": job.news_monitor_id,
        "news_task_id": job.news_task_id,
        "user_id": job.user_id,
        "analysis_type": job.analysis_type,
        "celery_task_id": job.celery_task_id,
        "status": job.status,
        "analysis_config": job.analysis_config,
        "source_task_ids": job.source_task_ids,
        "source_count": job.source_count,
        "analyzed_count": job.analyzed_count,
        "failed_count": job.failed_count,
        "result_data": job.result_data,
        "analysis_summary": job.analysis_summary,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "processing_time": job.processing_time,
        "token_usage": job.token_usage,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "social_monitor_name": row.social_monitor_name,
        "social_task_name": row.social_task_name,
        "news_monitor_name": row.news_monitor_name,
        "news_task_name": row.news_task_name,
        "user_name": row.user_name,
    }


async def _assert_job_access(db: AsyncSession, job: AnalysisJob, current_user_id: int) -> None:
    """验证用户对 AnalysisJob 的访问权限（按模块判断）"""
    if job.social_monitor_id:
        from src.social_media.monitors import crud as monitor_crud
        await monitor_crud.assert_monitor_access(
            db, job.social_monitor_id, current_user_id,
            detail="You don't have access to this analysis job"
        )
    elif job.news_monitor_id:
        from src.news_media.monitors.crud import get_monitor_by_id as get_news_monitor
        from src.rbac.utils import is_admin_or_super_admin
        from src.auth.models import User
        from sqlalchemy import select

        monitor = await get_news_monitor(db, job.news_monitor_id, load_relations=True)
        if not monitor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="News monitor not found",
            )
        # 检查用户权限
        user_stmt = select(User).where(User.id == current_user_id)
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if user and is_admin_or_super_admin(user):
            return
        if monitor.user_id != current_user_id and current_user_id not in {p.id for p in monitor.participants}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this analysis job",
            )


async def get_analysis_progress(
    db: AsyncSession, job_id: int, current_user_id: int
) -> AnalysisProgressResponse:
    """获取分析任务进度"""
    job = await _get_job_or_404(db, job_id)

    # 验证权限
    await _assert_job_access(db, job, current_user_id)

    # 计算进度（限制最大100%）
    progress = 0.0
    if job.source_count > 0:
        progress = min((job.analyzed_count / job.source_count) * 100, 100.0)

    # 估算剩余时间
    estimated_time_remaining = None
    if job.processing_time and job.analyzed_count > 0:
        avg_time_per_item = job.processing_time / job.analyzed_count
        remaining_items = job.source_count - job.analyzed_count
        estimated_time_remaining = int(avg_time_per_item * remaining_items)

    # 获取当前Token和成本
    current_tokens = 0
    current_cost = 0.0
    if job.token_usage:
        current_tokens = job.token_usage.get("summary", {}).get("total_tokens", 0)
        current_cost = job.token_usage.get("summary", {}).get("total_cost_cny", 0.0)

    return AnalysisProgressResponse(
        job_id=job_id,
        status=job.status,
        progress=progress,
        analyzed_count=job.analyzed_count,
        total_count=job.source_count,
        estimated_time_remaining=estimated_time_remaining,
        current_cost=current_cost,
        current_tokens=current_tokens,
    )


async def cancel_analysis_job(
    db: AsyncSession, job_id: int, current_user_id: int
) -> bool:
    """取消分析任务"""
    from celery import current_app as celery_app

    job = await _get_job_or_404(db, job_id)

    # 验证权限
    await _assert_job_access(db, job, current_user_id)

    if job.status not in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel analysis in status: {job.status}",
        )

    # 取消Celery任务
    celery_app.control.revoke(job.celery_task_id, terminate=True)

    # 更新状态
    job.status = "failed"
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()

    return True


async def delete_analysis_job(
    db: AsyncSession, job_id: int, current_user_id: int
) -> bool:
    """删除分析任务"""
    job = await _get_job_or_404(db, job_id)

    # 验证权限
    await _assert_job_access(db, job, current_user_id)

    await db.delete(job)
    await db.commit()

    return True
