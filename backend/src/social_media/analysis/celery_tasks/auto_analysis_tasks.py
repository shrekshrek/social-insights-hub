"""自动分析任务链

数据上传完成后自动执行全流程分析：
1. 原文初筛
2. 原文深度分析
3. 评论深度分析
4. 聚合报告生成
"""

import logging
import time
from typing import Any, Dict

from src.celery_app import celery_app
from src.config import settings
from src.database import SyncSessionLocal

logger = logging.getLogger(__name__)

# 默认阈值配置
DEFAULT_SPAM_MAX = 7.0
DEFAULT_VALUE_MIN = 4.0
DEFAULT_RELEVANCE_MIN = 4.0

# 任务等待超时（秒）
TASK_WAIT_TIMEOUT = 3600  # 1小时
POLL_INTERVAL = 5  # 5秒轮询一次


def _get_db_session():
    """获取同步数据库会话"""
    return SyncSessionLocal()


def _wait_for_analysis_job(job_id: int, timeout: int = TASK_WAIT_TIMEOUT) -> bool:
    """等待分析任务完成
    
    Returns:
        bool: 任务是否成功完成
    """
    from src.social_media.analysis.models import AnalysisJob
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        with _get_db_session() as db:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job:
                logger.error(f"Analysis job {job_id} not found")
                return False
            
            if job.status == "completed":
                logger.info(f"Analysis job {job_id} completed successfully")
                return True
            elif job.status == "failed":
                logger.error(f"Analysis job {job_id} failed: {job.error_message}")
                return False
            
            # 仍在处理中，继续等待
            logger.debug(f"Analysis job {job_id} status: {job.status}, waiting...")
        
        time.sleep(POLL_INTERVAL)
    
    logger.error(f"Analysis job {job_id} timed out after {timeout} seconds")
    return False


def _run_screening(task_id: int, user_id: int, project_keywords: str) -> int | None:
    """执行原文初筛
    
    Returns:
        分析任务ID，失败返回 None
    """
    from src.social_media.tasks.models import SocialPost, DataTask
    from .screening_tasks import run_screening_task
    
    with _get_db_session() as db:
        # 获取任务信息
        task = db.query(DataTask).filter(DataTask.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return None
        
        # 获取所有帖子ID
        post_ids = [
            row[0] for row in 
            db.query(SocialPost.id)
            .filter(SocialPost.task_id == task_id, SocialPost.is_deleted.is_(False))
            .all()
        ]
        
        if not post_ids:
            logger.info(f"Task {task_id}: No posts to screen")
            return None
        
        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.social_media.analysis.jobs import create_analysis_job_sync
        analysis_job = create_analysis_job_sync(
            db=db,
            project_id=task.project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type="screening_posts",
            source_count=len(post_ids),
        )
        job_id = analysis_job.id
        
        # 启动 Celery 任务
        celery_result = run_screening_task.delay(
            result_id=job_id,
            task_id=task_id,
            post_ids=post_ids,
            project_keywords=project_keywords,
        )
        
        # 更新为真实的 celery_task_id
        analysis_job.celery_task_id = celery_result.id
        db.commit()
        
        logger.info(f"Task {task_id}: Started screening job {job_id} for {len(post_ids)} posts")
        return job_id


def _run_deep_posts(
    task_id: int, 
    user_id: int,
    spam_max: float,
    value_min: float,
    relevance_min: float,
) -> int | None:
    """执行原文深度分析"""
    from src.social_media.analysis.models import PostAnalysis
    from src.social_media.tasks.models import DataTask
    from .deep_analysis_tasks import run_post_deep_task
    
    with _get_db_session() as db:
        task = db.query(DataTask).filter(DataTask.id == task_id).first()
        if not task:
            return None
        
        # 筛选符合阈值的帖子（已初筛但未深度分析）
        post_ids = [
            row[0] for row in
            db.query(PostAnalysis.post_id)
            .filter(
                PostAnalysis.task_id == task_id,
                PostAnalysis.spam_score.isnot(None),
                PostAnalysis.spam_score <= spam_max,
                PostAnalysis.value_score >= value_min,
                PostAnalysis.relevance_score >= relevance_min,
                PostAnalysis.deep_result.is_(None),  # 未做深度分析
            )
            .all()
        ]
        
        if not post_ids:
            logger.info(f"Task {task_id}: No posts for deep analysis")
            return None
        
        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.social_media.analysis.jobs import create_analysis_job_sync
        analysis_job = create_analysis_job_sync(
            db=db,
            project_id=task.project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type="deep_posts",
            source_count=len(post_ids),
        )
        job_id = analysis_job.id
        
        # 启动 Celery 任务
        celery_result = run_post_deep_task.delay(
            result_id=job_id,
            task_id=task_id,
            post_ids=post_ids,
            analysis_focus=task.keywords,
        )
        
        # 更新为真实的 celery_task_id
        analysis_job.celery_task_id = celery_result.id
        db.commit()
        
        logger.info(f"Task {task_id}: Started deep posts job {job_id} for {len(post_ids)} posts")
        return job_id


def _run_deep_comments(
    task_id: int,
    user_id: int,
    spam_max: float,
    value_min: float,
    relevance_min: float,
) -> int | None:
    """执行评论深度分析"""
    from src.social_media.analysis.models import PostAnalysis
    from src.social_media.tasks.models import DataTask, SocialComment
    from .deep_analysis_tasks import run_comment_deep_task
    
    with _get_db_session() as db:
        task = db.query(DataTask).filter(DataTask.id == task_id).first()
        if not task:
            return None
        
        # 筛选：已完成深度分析且有评论的帖子
        post_ids = [
            row[0] for row in
            db.query(PostAnalysis.post_id)
            .filter(
                PostAnalysis.task_id == task_id,
                PostAnalysis.spam_score <= spam_max,
                PostAnalysis.value_score >= value_min,
                PostAnalysis.relevance_score >= relevance_min,
                PostAnalysis.deep_result.isnot(None),  # 已完成深度分析
                PostAnalysis.comment_deep_result.is_(None),  # 未做评论深度
            )
            .all()
        ]
        
        # 过滤出实际有评论的帖子
        posts_with_comments = []
        for post_id in post_ids:
            comment_count = db.query(SocialComment).filter(
                SocialComment.post_id == post_id,
                SocialComment.is_deleted.is_(False),
            ).count()
            if comment_count > 0:
                posts_with_comments.append(post_id)
        
        if not posts_with_comments:
            logger.info(f"Task {task_id}: No posts with comments for deep analysis")
            return None
        
        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.social_media.analysis.jobs import create_analysis_job_sync
        analysis_job = create_analysis_job_sync(
            db=db,
            project_id=task.project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type="deep_comments",
            source_count=len(posts_with_comments),
        )
        job_id = analysis_job.id
        
        # 启动 Celery 任务
        celery_result = run_comment_deep_task.delay(
            result_id=job_id,
            task_id=task_id,
            post_ids=posts_with_comments,
            analysis_focus=task.keywords,
        )
        
        # 更新为真实的 celery_task_id
        analysis_job.celery_task_id = celery_result.id
        db.commit()
        
        logger.info(f"Task {task_id}: Started deep comments job {job_id} for {len(posts_with_comments)} posts")
        return job_id


def _run_aggregation(task_id: int, user_id: int) -> int | None:
    """执行聚合报告生成"""
    from src.social_media.tasks.models import DataTask
    from .aggregation_tasks import run_aggregation_task
    
    with _get_db_session() as db:
        task = db.query(DataTask).filter(DataTask.id == task_id).first()
        if not task:
            return None
        
        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.social_media.analysis.jobs import create_analysis_job_sync
        analysis_job = create_analysis_job_sync(
            db=db,
            project_id=task.project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type="aggregation",
            source_count=0,
        )
        job_id = analysis_job.id
        
        # 启动 Celery 任务
        celery_result = run_aggregation_task.delay(
            result_id=job_id,
            task_id=task_id,
        )
        
        # 更新为真实的 celery_task_id
        analysis_job.celery_task_id = celery_result.id
        db.commit()
        
        logger.info(f"Task {task_id}: Started aggregation job {job_id}")
        return job_id


@celery_app.task(
    name="analysis.auto.run",
    bind=True,
    max_retries=0,
)
def run_auto_analysis(
    self,
    task_id: int,
    user_id: int,
    project_keywords: str = "",
    spam_max: float = DEFAULT_SPAM_MAX,
    value_min: float = DEFAULT_VALUE_MIN,
    relevance_min: float = DEFAULT_RELEVANCE_MIN,
) -> Dict[str, Any]:
    """自动执行全流程分析
    
    按顺序执行：初筛 → 原文深度 → 评论深度 → 聚合报告
    """
    logger.info(f"Task {task_id}: Starting auto analysis pipeline")
    
    results = {
        "task_id": task_id,
        "screening": None,
        "deep_posts": None,
        "deep_comments": None,
        "aggregation": None,
        "status": "started",
    }
    
    try:
        # 1. 原文初筛
        logger.info(f"Task {task_id}: Step 1/4 - Running screening...")
        screening_job_id = _run_screening(task_id, user_id, project_keywords)
        results["screening"] = {"job_id": screening_job_id}
        
        if screening_job_id:
            if not _wait_for_analysis_job(screening_job_id):
                results["status"] = "failed_at_screening"
                logger.error(f"Task {task_id}: Screening failed, stopping pipeline")
                return results
            results["screening"]["status"] = "completed"
        else:
            results["screening"] = {"status": "skipped", "reason": "no_posts"}
        
        # 2. 原文深度分析
        logger.info(f"Task {task_id}: Step 2/4 - Running deep posts analysis...")
        deep_posts_job_id = _run_deep_posts(task_id, user_id, spam_max, value_min, relevance_min)
        results["deep_posts"] = {"job_id": deep_posts_job_id}
        
        if deep_posts_job_id:
            if not _wait_for_analysis_job(deep_posts_job_id):
                results["status"] = "failed_at_deep_posts"
                logger.error(f"Task {task_id}: Deep posts analysis failed, stopping pipeline")
                return results
            results["deep_posts"]["status"] = "completed"
        else:
            results["deep_posts"] = {"status": "skipped", "reason": "no_qualified_posts"}
        
        # 3. 评论深度分析
        logger.info(f"Task {task_id}: Step 3/4 - Running deep comments analysis...")
        deep_comments_job_id = _run_deep_comments(task_id, user_id, spam_max, value_min, relevance_min)
        results["deep_comments"] = {"job_id": deep_comments_job_id}
        
        if deep_comments_job_id:
            if not _wait_for_analysis_job(deep_comments_job_id):
                results["status"] = "failed_at_deep_comments"
                logger.error(f"Task {task_id}: Deep comments analysis failed, stopping pipeline")
                return results
            results["deep_comments"]["status"] = "completed"
        else:
            results["deep_comments"] = {"status": "skipped", "reason": "no_posts_with_comments"}
        
        # 4. 聚合报告生成
        logger.info(f"Task {task_id}: Step 4/4 - Running aggregation...")
        aggregation_job_id = _run_aggregation(task_id, user_id)
        results["aggregation"] = {"job_id": aggregation_job_id}
        
        if aggregation_job_id:
            if not _wait_for_analysis_job(aggregation_job_id):
                results["status"] = "failed_at_aggregation"
                logger.error(f"Task {task_id}: Aggregation failed")
                return results
            results["aggregation"]["status"] = "completed"
        else:
            results["aggregation"] = {"status": "skipped", "reason": "unknown"}
        
        results["status"] = "completed"
        logger.info(f"Task {task_id}: Auto analysis pipeline completed successfully")
        
    except Exception as e:
        logger.exception(f"Task {task_id}: Auto analysis pipeline failed with error: {e}")
        results["status"] = "error"
        results["error"] = str(e)
    
    return results

