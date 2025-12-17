"""AnalysisJob 工厂函数

统一 AnalysisJob 的创建和更新逻辑，支持同步和异步两种模式。
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from src.social_media.analysis.models import AnalysisJob


def create_analysis_job_sync(
    db: Session,
    project_id: int,
    task_id: int,
    user_id: int,
    analysis_type: str,
    source_count: int,
    celery_task_id: str = "",
    analysis_config: dict | None = None,
    status: str = "pending",
) -> AnalysisJob:
    """同步创建 AnalysisJob 记录

    Args:
        db: 同步数据库会话
        project_id: 项目ID
        task_id: 任务ID
        user_id: 用户ID
        analysis_type: 分析类型 (AnalysisType 枚举值)
        source_count: 源数据数量
        celery_task_id: Celery 任务ID，同步任务传空或伪ID
        analysis_config: 分析配置参数
        status: 初始状态，默认 "pending"

    Returns:
        AnalysisJob: 创建的分析任务记录
    """
    # 同步任务使用伪 celery_task_id
    if not celery_task_id:
        celery_task_id = f"sync-{analysis_type}-{uuid.uuid4().hex[:8]}"

    job = AnalysisJob(
        project_id=project_id,
        task_id=task_id,
        user_id=user_id,
        analysis_type=analysis_type,
        celery_task_id=celery_task_id,
        status=status,
        source_count=source_count,
        analysis_config=analysis_config,
        started_at=datetime.now(timezone.utc) if status == "processing" else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def create_analysis_job_async(
    db: AsyncSession,
    project_id: int,
    task_id: int | None,
    user_id: int,
    analysis_type: str,
    source_count: int,
    celery_task_id: str = "",
    analysis_config: dict | None = None,
    status: str = "pending",
) -> AnalysisJob:
    """异步创建 AnalysisJob 记录

    Args:
        db: 异步数据库会话
        project_id: 项目ID
        task_id: 任务ID
        user_id: 用户ID
        analysis_type: 分析类型 (AnalysisType 枚举值)
        source_count: 源数据数量
        celery_task_id: Celery 任务ID，为空时生成唯一伪 ID（后续可更新为真实 ID）
        analysis_config: 分析配置参数
        status: 初始状态，默认 "pending"

    Returns:
        AnalysisJob: 创建的分析任务记录
    """
    # 生成伪 celery_task_id（避免唯一约束冲突）
    # 格式与同步版本一致：pending-{type}-{uuid}
    if not celery_task_id:
        celery_task_id = f"pending-{analysis_type}-{uuid.uuid4().hex[:8]}"
    
    job = AnalysisJob(
        project_id=project_id,
        task_id=task_id,
        user_id=user_id,
        analysis_type=analysis_type,
        celery_task_id=celery_task_id,
        status=status,
        source_count=source_count,
        analysis_config=analysis_config,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def complete_analysis_job_sync(
    db: Session,
    job: AnalysisJob,
    analyzed_count: int = 0,
    token_usage: dict[str, Any] | None = None,
    result_data: dict | None = None,
    error_message: str | None = None,
) -> AnalysisJob:
    """同步完成 AnalysisJob

    Args:
        db: 同步数据库会话
        job: 要更新的任务
        analyzed_count: 成功分析数量
        token_usage: Token 使用统计
        result_data: 结果数据
        error_message: 错误信息（如果失败）

    Returns:
        AnalysisJob: 更新后的任务
    """
    job.completed_at = datetime.now(timezone.utc)

    if error_message:
        job.status = "failed"
        job.error_message = error_message
    else:
        job.status = "completed"

    job.analyzed_count = analyzed_count

    if job.started_at:
        job.processing_time = int((job.completed_at - job.started_at).total_seconds())

    if token_usage:
        job.token_usage = token_usage

    if result_data:
        job.result_data = result_data

    db.commit()
    return job


def start_analysis_job_sync(db: Session, job_or_id: AnalysisJob | int) -> AnalysisJob | None:
    """同步标记任务开始处理

    Args:
        db: 同步数据库会话
        job_or_id: AnalysisJob 对象或 job_id

    Returns:
        AnalysisJob: 更新后的任务，如果找不到则返回 None
    """
    if isinstance(job_or_id, int):
        from sqlalchemy import select
        stmt = select(AnalysisJob).where(AnalysisJob.id == job_or_id)
        result = db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return None
    else:
        job = job_or_id
    
    job.status = "processing"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    return job
