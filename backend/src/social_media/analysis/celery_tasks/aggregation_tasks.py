"""聚合分析 Celery 任务

将聚合分析改为异步执行，避免阻塞 FastAPI 事件循环。

注意：聚合分析本身不涉及 LLM，不创建 AnalysisJob 记录。
但内部的实体归一化和观点归一化会各自创建 AnalysisJob 记录。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import select

from src.celery_app import celery_app
from src.database import SyncSessionLocal
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
    task_id: int,
    project_id: int | None = None,
    user_id: int | None = None,
    entity_job_id: int | None = None,
    opinion_job_id: int | None = None,
) -> Dict[str, Any]:
    """执行聚合分析（Celery 异步任务）
    
    聚合分析本身不涉及 LLM API 调用。
    实体归一化和观点归一化的 AnalysisJob 由调用方预先创建（状态为 pending），
    本任务接收 job_id 并传递给 orchestrator 更新状态。
    
    Args:
        task_id: DataTask ID
        project_id: 项目 ID
        user_id: 用户 ID
        entity_job_id: 预创建的实体归一化 AnalysisJob ID
        opinion_job_id: 预创建的观点归一化 AnalysisJob ID
    
    Returns:
        聚合分析结果
    """
    logger.info(f"开始聚合分析: task_id={task_id}")
    
    db = SyncSessionLocal()
    try:
        # 执行聚合分析，传递预创建的 job_id
        aggregation_result = aggregate_task_analysis(
            db=db,
            task_id=task_id,
            project_id=project_id,
            user_id=user_id,
            entity_job_id=entity_job_id,
            opinion_job_id=opinion_job_id,
        )
        
        # 将结果保存到 DataTask.analysis_result
        now = datetime.now(timezone.utc)
        stmt = select(DataTask).where(DataTask.id == task_id)
        result = db.execute(stmt)
        data_task = result.scalar_one_or_none()
        
        if data_task:
            data_task.analysis_result = aggregation_result
            data_task.analysis_result_at = now
        
        db.commit()
        
        logger.info(f"聚合分析完成: task_id={task_id}")
        
        return {
            "status": "completed",
            "task_id": task_id,
            "analyzed_at": now.isoformat(),
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"聚合分析失败: task_id={task_id}, error={str(e)}", exc_info=True)
        
        # 重试或抛出异常
        raise self.retry(exc=e)
        
    finally:
        db.close()
