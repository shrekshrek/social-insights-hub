"""AnalysisJob CRUD 操作

提供 AnalysisJob 的查询、更新、删除等操作。
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from fastapi import HTTPException, status

from src.social_media.analysis.models import AnalysisJob
from src.social_media.analysis.schemas import AnalysisProgressResponse


async def get_analysis_jobs(
    db: AsyncSession,
    current_user_id: int,
    page: int = 1,
    page_size: int = 20,
    project_id: int | None = None,
    task_id: int | None = None,
    analysis_type: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[List[Dict[str, Any]], int]:
    """获取全局分析任务列表（带筛选和关联信息）"""
    from src.social_media.projects.models import SocialProject
    from src.social_media.tasks.models import DataTask
    from src.auth.models import User

    # 构建基础查询
    stmt = (
        select(
            AnalysisJob,
            SocialProject.name.label('project_name'),
            DataTask.name.label('task_name'),
            User.username.label('user_name'),
        )
        .join(SocialProject, AnalysisJob.project_id == SocialProject.id)
        .join(DataTask, AnalysisJob.task_id == DataTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
    )

    # 筛选条件
    conditions = []

    if project_id is not None:
        conditions.append(AnalysisJob.project_id == project_id)

    if task_id is not None:
        conditions.append(AnalysisJob.task_id == task_id)

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

    # 转换为字典列表（包含关联名称）
    items = []
    for row in rows:
        job = row.AnalysisJob
        item = {
            "id": job.id,
            "project_id": job.project_id,
            "task_id": job.task_id,
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
            "project_name": row.project_name,
            "task_name": row.task_name,
            "user_name": row.user_name,
        }
        items.append(item)

    return items, total


async def get_analysis_job(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> Optional[Dict[str, Any]]:
    """获取单个分析任务详情（带关联信息）"""
    from src.social_media.projects.models import SocialProject
    from src.social_media.tasks.models import DataTask
    from src.auth.models import User
    from src.social_media.projects import crud as project_crud

    # 查询分析任务及关联信息
    stmt = (
        select(
            AnalysisJob,
            SocialProject.name.label('project_name'),
            DataTask.name.label('task_name'),
            User.username.label('user_name'),
        )
        .join(SocialProject, AnalysisJob.project_id == SocialProject.id)
        .join(DataTask, AnalysisJob.task_id == DataTask.id, isouter=True)
        .join(User, AnalysisJob.user_id == User.id)
        .where(AnalysisJob.id == job_id)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return None

    job = row.AnalysisJob

    # 验证用户权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this analysis job"
        )

    return {
        "id": job.id,
        "project_id": job.project_id,
        "task_id": job.task_id,
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
        "project_name": row.project_name,
        "task_name": row.task_name,
        "user_name": row.user_name,
    }


async def get_analysis_progress(
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> AnalysisProgressResponse:
    """获取分析任务进度"""
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    # 计算进度
    progress = 0.0
    if job.source_count > 0:
        progress = (job.analyzed_count / job.source_count) * 100

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
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> bool:
    """取消分析任务"""
    from celery import current_app as celery_app
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    if job.status not in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel analysis in status: {job.status}"
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
    db: AsyncSession,
    job_id: int,
    current_user_id: int
) -> bool:
    """删除分析任务"""
    from src.social_media.projects import crud as project_crud

    # 查询分析任务
    stmt = select(AnalysisJob).where(AnalysisJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job {job_id} not found"
        )

    # 验证权限
    has_access = await project_crud.check_project_access(db, job.project_id, current_user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this analysis job"
        )

    await db.delete(job)
    await db.commit()

    return True
