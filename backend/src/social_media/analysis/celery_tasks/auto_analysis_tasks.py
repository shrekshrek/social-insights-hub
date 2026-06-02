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
from src.database import SyncSessionLocal
from src.redis_sync_client import get_sync_redis

logger = logging.getLogger(__name__)

# 默认阈值配置
DEFAULT_SPAM_MAX = 10.0
DEFAULT_VALUE_MIN = 4.0
DEFAULT_RELEVANCE_MIN = 4.0

# 任务等待超时（秒）
TASK_WAIT_TIMEOUT = 3600  # 1小时
POLL_INTERVAL = 5  # 5秒轮询一次


def _get_db_session():
    """获取同步数据库会话"""
    return SyncSessionLocal()


def _auto_lock_key(task_id: int) -> str:
    # 执行侧“正在运行”锁（与触发侧 triggered key 分离）
    return f"analysis:auto:{task_id}:running"


def _acquire_auto_lock(task_id: int, owner: str, ttl_seconds: int) -> bool:
    """task_id 级自动分析幂等锁（防止同一任务重复启动自动分析链）"""
    redis_client = get_sync_redis()
    return bool(
        redis_client.set(_auto_lock_key(task_id), owner, nx=True, ex=ttl_seconds)
    )


def _release_auto_lock(task_id: int, owner: str) -> None:
    """仅当 owner 匹配时释放锁，避免误删他人锁。"""
    redis_client = get_sync_redis()
    key = _auto_lock_key(task_id)
    try:
        current = redis_client.get(key)
        if current == owner:
            redis_client.delete(key)
    except Exception:
        # 锁释放失败不应影响主流程；依赖 TTL 自动过期兜底
        logger.exception("Failed to release auto analysis lock")


def _wait_for_analysis_job(job_id: int, timeout: int = TASK_WAIT_TIMEOUT) -> bool:
    """等待分析任务完成

    Returns:
        bool: 任务是否成功完成
    """
    from src.jobs.models import AnalysisJob

    start_time = time.time()

    while time.time() - start_time < timeout:
        with _get_db_session() as db:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job:
                logger.error("Analysis job %s not found", job_id)
                return False

            if job.status == "completed":
                logger.info("Analysis job %s completed successfully", job_id)
                return True
            elif job.status == "failed":
                logger.error("Analysis job %s failed: %s", job_id, job.error_message)
                return False

            # 仍在处理中，继续等待
            logger.debug("Analysis job %s status: %s, waiting...", job_id, job.status)

        time.sleep(POLL_INTERVAL)

    logger.error("Analysis job %s timed out after %s seconds", job_id, timeout)
    return False


def _run_screening(task_id: int, user_id: int, monitor_keywords: str) -> int | None:
    """执行原文初筛

    Returns:
        分析任务ID，失败返回 None
    """
    from src.social_media.tasks.models import SocialPost, SocialTask as SocialTask
    from src.social_media.analysis.models import PostAnalysis
    from .screening_tasks import run_screening_task

    with _get_db_session() as db:
        # 获取任务信息
        task = db.query(SocialTask).filter(SocialTask.id == task_id).first()
        if not task:
            logger.error("Task %s not found", task_id)
            return None

        # 获取任务下所有原文ID（排除已有初筛结果的），与手动初筛逻辑保持一致
        post_ids = [
            row[0]
            for row in (
                db.query(SocialPost.id)
                .outerjoin(PostAnalysis, PostAnalysis.post_id == SocialPost.id)
                .filter(SocialPost.task_id == task_id)
                .filter(SocialPost.is_deleted.is_(False))
                .filter(PostAnalysis.spam_score.is_(None))  # 只选择尚未初筛的
                .all()
            )
        ]

        if not post_ids:
            logger.info("Task %s: No posts to screen (already screened)", task_id)
            return None

        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.jobs import create_analysis_job_sync

        analysis_job = create_analysis_job_sync(
            db=db,
            social_monitor_id=task.monitor_id,
            social_task_id=task_id,
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
            monitor_keywords=monitor_keywords,
        )

        # 更新为真实的 celery_task_id
        analysis_job.celery_task_id = celery_result.id
        db.commit()

        logger.info(
            "Task %s: Started screening job %s for %s posts",
            task_id,
            job_id,
            len(post_ids),
        )
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
    from src.social_media.tasks.models import SocialTask as SocialTask, SocialPost
    from .deep_analysis_tasks import run_post_deep_task

    with _get_db_session() as db:
        task = db.query(SocialTask).filter(SocialTask.id == task_id).first()
        if not task:
            return None

        # 筛选符合阈值的原文（已初筛但未深度分析）
        post_ids = [
            row[0]
            for row in (
                db.query(PostAnalysis.post_id)
                .join(SocialPost, SocialPost.id == PostAnalysis.post_id)
                .filter(PostAnalysis.task_id == task_id)
                .filter(SocialPost.is_deleted.is_(False))
                .filter(PostAnalysis.spam_score.isnot(None))
                .filter(PostAnalysis.spam_score <= spam_max)
                .filter(PostAnalysis.value_score >= value_min)
                .filter(PostAnalysis.relevance_score >= relevance_min)
                .filter(PostAnalysis.post_deep_result.is_(None))  # 未做深度分析
                .all()
            )
        ]

        if not post_ids:
            logger.info("Task %s: No posts for deep analysis", task_id)
            return None

        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.jobs import create_analysis_job_sync

        analysis_job = create_analysis_job_sync(
            db=db,
            social_monitor_id=task.monitor_id,
            social_task_id=task_id,
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

        logger.info(
            "Task %s: Started deep posts job %s for %s posts",
            task_id,
            job_id,
            len(post_ids),
        )
        return job_id


def _run_deep_comments(
    task_id: int,
    user_id: int,
    spam_max: float,
    value_min: float,
    relevance_min: float,
) -> int | None:
    """执行评论深度分析

    与手动候选筛选保持一致：post_deep_result 已有 + comment_deep_result 为空 + 原文有评论
    （不额外按阈值过滤，避免与现有 preview 逻辑产生分歧）
    """
    from src.social_media.analysis.models import PostAnalysis
    from src.social_media.tasks.models import SocialTask as SocialTask, SocialPost
    from .deep_analysis_tasks import run_comment_deep_task

    with _get_db_session() as db:
        task = db.query(SocialTask).filter(SocialTask.id == task_id).first()
        if not task:
            return None

        posts_with_comments = [
            row[0]
            for row in (
                db.query(PostAnalysis.post_id)
                .join(SocialPost, SocialPost.id == PostAnalysis.post_id)
                .filter(PostAnalysis.task_id == task_id)
                .filter(SocialPost.is_deleted.is_(False))
                .filter(PostAnalysis.post_deep_result.isnot(None))  # 已完成原文深度
                .filter(PostAnalysis.comment_deep_result.is_(None))  # 未做评论深度
                .filter((SocialPost.comments_count or 0) > 0)
                .all()
            )
        ]

        if not posts_with_comments:
            logger.info("Task %s: No posts with comments for deep analysis", task_id)
            return None

        # 创建分析任务记录（使用工厂函数，会自动生成临时 celery_task_id）
        from src.jobs import create_analysis_job_sync

        analysis_job = create_analysis_job_sync(
            db=db,
            social_monitor_id=task.monitor_id,
            social_task_id=task_id,
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

        logger.info(
            "Task %s: Started deep comments job %s for %s posts",
            task_id,
            job_id,
            len(posts_with_comments),
        )
        return job_id


def _run_aggregation(
    task_id: int,
    user_id: int,
    skip_llm_normalization: bool = False,
) -> int | None:
    """执行聚合报告生成

    Args:
        task_id: SocialTask ID
        user_id: 用户 ID
        skip_llm_normalization: probe 轻量路径。True 时不创建 entity/opinion
            归一化的 AnalysisJob（没 LLM 调用可记录），直接派发 celery 任务并
            让 orchestrator 跳过 LLM 归一化。返回 None（无 job_id 可跟踪）

    返回的 job id 仅供 `run_auto_analysis` 的 `_wait_for_analysis_job` 阻塞等待。
    轻量路径下无需阻塞（聚合 <5s），直接返回 None 不会让主流程出错——
    `run_auto_analysis` 里有 `if aggregation_job_id: wait` 的分支处理。
    """
    from sqlalchemy import func
    from src.social_media.tasks.models import SocialTask as SocialTask
    from src.social_media.analysis.models import PostAnalysis
    from src.jobs import create_analysis_job_sync
    from .aggregation_tasks import run_aggregation_task

    with _get_db_session() as db:
        task = db.query(SocialTask).filter(SocialTask.id == task_id).first()
        if not task:
            return None

        # 检查是否有已分析的原文
        analyzed_count = (
            db.query(func.count())
            .filter(
                PostAnalysis.task_id == task_id,
                PostAnalysis.spam_score.isnot(None),
            )
            .scalar()
            or 0
        )

        # 轻量路径：不创建 entity/opinion AnalysisJob，不派发额外 celery，不调 LLM
        # 走独立的 build_probe_aggregation（probe_lite.py），只产出 probe review chain
        # 需要的 4 个字段（posts_count/deep_analyzed/entity_match/top_topics/promotion_ratio）。
        # 结果 shape 是完整 aggregation 的严格子集，字段路径一致。
        # collect 阶段跑完整 aggregation 时会覆写这个轻量结果。
        #
        # 即使 analyzed_count == 0 仍走 probe_lite：probe_lite 对空 analyses 健壮（产出
        # screened=0/deep_analyzed=0 的骨架），让 task.analysis_result 非 NULL 进入终态。
        # 否则当 screening 全部失败（如 LLM 偶发返回非 JSON）时 task 永久卡 probe_ready，
        # 整个策略卡 probing 死锁。空骨架交给 probe review chain 自行判（deep_analyzed<8
        # → 样本不足 pass 待全量验证）
        if skip_llm_normalization:
            from datetime import datetime, timezone
            from .aggregation.probe_lite import build_probe_aggregation

            aggregation_result = build_probe_aggregation(db, task_id)
            task.analysis_result = aggregation_result
            task.analysis_result_at = datetime.now(timezone.utc)
            db.commit()

            if analyzed_count == 0:
                logger.warning(
                    "Task %s: Probe aggregation written with 0 valid analyses "
                    "(screening produced no PostAnalysis rows; likely LLM call failure)",
                    task_id,
                )
            else:
                logger.info(
                    "Task %s: Lightweight probe aggregation completed (%s entities, %s topics)",
                    task_id,
                    len(aggregation_result["insights"]["target_entities"])
                    + len(aggregation_result["insights"]["competitor_entities"]),
                    len(aggregation_result["insights"]["top_topics"]),
                )
            # 返回 None：probe 阶段没有 AnalysisJob 可供外层 _wait_for_analysis_job 等待；
            # 聚合已同步完成，outer run_auto_analysis 看到 None 会标 completed_inline 直接返回
            return None

        if analyzed_count == 0:
            logger.info("Task %s: No analyzed posts for aggregation", task_id)
            return None

        # 创建实体归一化任务（和手动聚合一致）
        entity_job = create_analysis_job_sync(
            db=db,
            social_monitor_id=task.monitor_id,
            social_task_id=task_id,
            user_id=user_id,
            analysis_type="entity_normalization",
            source_count=analyzed_count,
        )

        # 创建观点归一化任务（和手动聚合一致）
        opinion_job = create_analysis_job_sync(
            db=db,
            social_monitor_id=task.monitor_id,
            social_task_id=task_id,
            user_id=user_id,
            analysis_type="opinion_normalization",
            source_count=analyzed_count,
        )

        # 启动 Celery 任务，传递预创建的 job_id
        celery_result = run_aggregation_task.delay(
            task_id=task_id,
            monitor_id=task.monitor_id,
            user_id=user_id,
            entity_job_id=entity_job.id,
            opinion_job_id=opinion_job.id,
        )

        # 仅更新 entity_job 的 celery_task_id 为真实任务ID：
        # - `analysis_jobs.celery_task_id` 有唯一约束，不能对两个 job 写同一个值
        # - 前端跟踪通常以 entity_job 为主，重传覆盖撤销也依赖真实 task_id
        entity_job.celery_task_id = celery_result.id
        db.commit()

        logger.info(
            "Task %s: Started aggregation (entity_job=%s, opinion_job=%s)",
            task_id,
            entity_job.id,
            opinion_job.id,
        )
        return entity_job.id


@celery_app.task(
    name="analysis.auto.run",
    bind=True,
    max_retries=0,
)
def run_auto_analysis(
    self,
    task_id: int,
    user_id: int,
    monitor_keywords: str = "",
    spam_max: float = DEFAULT_SPAM_MAX,
    value_min: float = DEFAULT_VALUE_MIN,
    relevance_min: float = DEFAULT_RELEVANCE_MIN,
    skip_llm_normalization: bool = False,
) -> Dict[str, Any]:
    """自动执行全流程分析

    按顺序执行：初筛 → 原文深度 → 评论深度 → 聚合报告

    Args:
        skip_llm_normalization: probe 轻量路径。True 时聚合步骤跳过 entity/opinion
            LLM 归一化，聚合 wall time 从 60-90s 降到 <5s。由 upload_result 根据
            task.phase 传入：probe=True，collect=False（collect 需要完整归一化供
            切片消费 aggregated_opinions / aggregated_entities）
    """
    logger.info("Task %s: Starting auto analysis pipeline", task_id)

    # 幂等锁（执行侧兜底）：即使触发侧并发，也保证同一 task 只跑一个自动分析链
    owner = getattr(self.request, "id", None) or f"auto-{int(time.time())}"
    # TTL 需覆盖整个 pipeline（4 步 × 单步超时 + 余量）
    lock_ttl = TASK_WAIT_TIMEOUT * 4 + 600
    if not _acquire_auto_lock(task_id, owner=owner, ttl_seconds=lock_ttl):
        logger.info(
            f"Task {task_id}: Auto analysis already running (lock exists), skip"
        )
        return {"task_id": task_id, "status": "skipped", "reason": "already_running"}

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
        logger.info("Task %s: Step 1/4 - Running screening...", task_id)
        screening_job_id = _run_screening(task_id, user_id, monitor_keywords)
        results["screening"] = {"job_id": screening_job_id}

        if screening_job_id:
            if not _wait_for_analysis_job(screening_job_id):
                results["status"] = "failed_at_screening"
                logger.error("Task %s: Screening failed, stopping pipeline", task_id)
                return results
            results["screening"]["status"] = "completed"
        else:
            results["screening"] = {"status": "skipped", "reason": "no_posts"}

        # 2. 原文深度分析
        logger.info("Task %s: Step 2/4 - Running deep posts analysis...", task_id)
        deep_posts_job_id = _run_deep_posts(
            task_id, user_id, spam_max, value_min, relevance_min
        )
        results["deep_posts"] = {"job_id": deep_posts_job_id}

        if deep_posts_job_id:
            if not _wait_for_analysis_job(deep_posts_job_id):
                results["status"] = "failed_at_deep_posts"
                logger.error(
                    "Task %s: Deep posts analysis failed, stopping pipeline", task_id
                )
                return results
            results["deep_posts"]["status"] = "completed"
        else:
            results["deep_posts"] = {
                "status": "skipped",
                "reason": "no_qualified_posts",
            }

        # 3. 评论深度分析
        logger.info("Task %s: Step 3/4 - Running deep comments analysis...", task_id)
        deep_comments_job_id = _run_deep_comments(
            task_id, user_id, spam_max, value_min, relevance_min
        )
        results["deep_comments"] = {"job_id": deep_comments_job_id}

        if deep_comments_job_id:
            if not _wait_for_analysis_job(deep_comments_job_id):
                results["status"] = "failed_at_deep_comments"
                logger.error(
                    "Task %s: Deep comments analysis failed, stopping pipeline", task_id
                )
                return results
            results["deep_comments"]["status"] = "completed"
        else:
            results["deep_comments"] = {
                "status": "skipped",
                "reason": "no_posts_with_comments",
            }

        # 4. 聚合报告生成
        logger.info(
            "Task %s: Step 4/4 - Running aggregation (skip_llm=%s)...",
            task_id,
            skip_llm_normalization,
        )
        aggregation_job_id = _run_aggregation(
            task_id,
            user_id,
            skip_llm_normalization=skip_llm_normalization,
        )
        results["aggregation"] = {"job_id": aggregation_job_id}

        if aggregation_job_id:
            if not _wait_for_analysis_job(aggregation_job_id):
                results["status"] = "failed_at_aggregation"
                logger.error("Task %s: Aggregation failed", task_id)
                return results
            results["aggregation"]["status"] = "completed"
        elif skip_llm_normalization:
            # probe 轻量路径：aggregation 已在 _run_aggregation 里同步完成
            results["aggregation"] = {"status": "completed_inline"}
        else:
            results["aggregation"] = {"status": "skipped", "reason": "unknown"}

        results["status"] = "completed"
        logger.info("Task %s: Auto analysis pipeline completed successfully", task_id)

    except Exception as e:
        logger.exception(
            "Task %s: Auto analysis pipeline failed with error: %s", task_id, e
        )
        results["status"] = "error"
        results["error"] = str(e)
    finally:
        _release_auto_lock(task_id, owner=owner)

    return results
