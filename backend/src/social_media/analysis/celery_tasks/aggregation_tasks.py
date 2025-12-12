"""聚合分析 Celery 任务

将聚合分析改为异步执行，避免阻塞 FastAPI 事件循环。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select

from src.celery_app import celery_app
from src.database import SyncSessionLocal
from src.social_media.analysis.models import AnalysisJob
from src.social_media.tasks.models import DataTask
from .aggregation import aggregate_task_analysis

logger = logging.getLogger(__name__)


@celery_app.task(
    name="analysis.aggregation.run",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def run_aggregation_task(
    self,
    result_id: int,
    task_id: int,
    project_id: int | None = None,
    user_id: int | None = None,
) -> Dict[str, Any]:
    """执行聚合分析（Celery 异步任务）
    
    Args:
        result_id: AnalysisJob ID，用于跟踪任务状态（与其他分析任务命名一致）
        task_id: DataTask ID
        project_id: 项目 ID（可选）
        user_id: 用户 ID（可选）
    
    Returns:
        聚合分析结果
    """
    logger.info(f"开始聚合分析: result_id={result_id}, task_id={task_id}")
    
    db = SyncSessionLocal()
    try:
        # 1. 更新任务状态为 processing
        _update_job_status(db, result_id, "processing")
        
        # 2. 执行聚合分析
        aggregation_result = aggregate_task_analysis(
            db=db,
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
        )
        
        # 3. 将结果保存到 DataTask.analysis_result
        now = datetime.now(timezone.utc)
        stmt = select(DataTask).where(DataTask.id == task_id)
        result = db.execute(stmt)
        data_task = result.scalar_one_or_none()
        
        if data_task:
            data_task.analysis_result = aggregation_result
            data_task.analysis_result_at = now
        
        # 4. 更新任务状态为 completed
        _update_job_status(
            db, result_id, "completed",
            result_data=aggregation_result
        )
        
        db.commit()
        
        logger.info(f"聚合分析完成: result_id={result_id}, task_id={task_id}")
        
        return {
            "status": "completed",
            "task_id": task_id,
            "result_id": result_id,
            "analyzed_at": now.isoformat(),
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"聚合分析失败: result_id={result_id}, error={str(e)}", exc_info=True)
        
        # 更新任务状态为 failed
        try:
            _update_job_status(db, result_id, "failed", error_message=str(e))
            db.commit()
        except Exception:
            pass
        
        # 重试或抛出异常
        raise self.retry(exc=e)
        
    finally:
        db.close()


def _update_job_status(
    db,
    result_id: int,
    status: str,
    result_data: dict | None = None,
    error_message: str | None = None,
):
    """更新 AnalysisJob 状态"""
    stmt = select(AnalysisJob).where(AnalysisJob.id == result_id)
    result = db.execute(stmt)
    job = result.scalar_one_or_none()
    
    if job:
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        
        if status == "processing" and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        
        if status == "completed":
            job.completed_at = datetime.now(timezone.utc)
            if job.started_at:
                job.processing_time = (job.completed_at - job.started_at).total_seconds()
            # 聚合分析的结果保存在 DataTask.analysis_result，而非 job.result_data
            # 但可以保存一个简单的成功标记
            job.result_data = {"success": True}
        
        if status == "failed" and error_message:
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)
