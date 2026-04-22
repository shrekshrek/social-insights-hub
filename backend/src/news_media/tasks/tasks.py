"""新闻媒体 Celery 任务（同步版）

将新闻全量采集（爬取 + 逐篇标注）转为同步 Celery 任务，
对齐社媒分析模块的架构：使用 SyncSessionLocal + gevent monkey-patch，
避免 asyncio event loop 与 gevent greenlet 之间的竞态（async_engine.dispose
在多 Celery 任务并发下会导致 asyncpg 连接池损坏，greenlet 永久卡住）。

insight 分析由切片（NewsSlice）按需触发，不在采集阶段执行。
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="news_media.run_probe",
    bind=True,
    max_retries=0,
)
def run_news_probe_task(self, task_id: int) -> None:
    """执行新闻探测 Celery 任务（仅搜索 + 落库，无 LLM）"""
    from src.database import SyncSessionLocal
    from src.news_media.tasks.models import NewsTask
    from src.news_media.tasks.service import execute_news_probe_sync

    with SyncSessionLocal() as db:
        task = db.get(NewsTask, task_id)
        if not task:
            logger.error("NewsTask %d not found, aborting probe", task_id)
            return
        try:
            execute_news_probe_sync(db, task)
            db.commit()
        except Exception as exc:
            logger.error("NewsTask %d: probe celery failed: %s", task_id, exc, exc_info=True)
            db.rollback()


@celery_app.task(
    name="news_media.run_collect",
    bind=True,
    max_retries=0,
)
def run_news_collect_task(
    self,
    task_id: int,
    tagging_job_id: int | None,
    analysis_goal: str = "",
) -> None:
    """执行新闻全量采集 Celery 任务（同步版）

    流程：
    1. 多渠道搜索 + 存文章
    2. Crawl4AI 抓全文
    3. 逐篇标注（NEWS_TAGGING job）
    4. 更新 NewsTask 状态

    insight 分析由 NewsSlice 按需触发，不在采集阶段执行。

    Args:
        task_id: NewsTask ID
        tagging_job_id: 逐篇标注的 AnalysisJob ID
        analysis_goal: 分析目标（可选，默认用任务关键词）
    """
    from src.database import SyncSessionLocal
    from src.jobs.factory import (
        complete_analysis_job_sync,
        start_analysis_job_sync,
    )
    from src.jobs.models import AnalysisJob
    from src.news_media.tasks.article_crawler import crawl_articles
    from src.news_media.tasks.models import NewsArticle, NewsTask
    from src.news_media.tasks.service import (
        _apply_tags_to_articles_sync,
        _resolve_channels,
        _search_and_store_articles_sync,
        _tag_articles_batch_sync,
    )

    with SyncSessionLocal() as db:
        task = db.get(NewsTask, task_id)
        if not task:
            logger.error("NewsTask %d not found, aborting", task_id)
            return

        tagging_job = db.get(AnalysisJob, tagging_job_id) if tagging_job_id else None
        goal = analysis_goal or task.keywords

        try:
            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            if tagging_job:
                start_analysis_job_sync(db, tagging_job)
            else:
                db.commit()

            raw_counts: dict[str, int] = {}
            articles = _search_and_store_articles_sync(
                db, task,
                max_results=20,
                channels=_resolve_channels(task),
                raw_counts_out=raw_counts,
            )

            if not articles:
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                task.articles_count = 0
                task.analysis_result = {
                    "meta": {
                        "keywords": task.keywords,
                        "articles_total": 0,
                        "channel_raw_counts": raw_counts,
                    },
                }
                if tagging_job:
                    complete_analysis_job_sync(db, tagging_job, analyzed_count=0)
                else:
                    db.commit()
                return

            urls = [a.url for a in articles]
            crawl_results = crawl_articles(urls)

            articles_crawled = 0
            for article in articles:
                full_text = crawl_results.get(article.url)
                if full_text:
                    article.full_text = full_text
                    articles_crawled += 1
            db.flush()

            # 查询任务下所有已落库文章（含原有文章）
            stmt = (
                select(NewsArticle)
                .where(and_(NewsArticle.task_id == task.id))
                .limit(200)
                .order_by(NewsArticle.published_at.desc().nulls_last())
            )
            all_articles = list(db.execute(stmt).scalars().all())

            tags, tag_token_usage = _tag_articles_batch_sync(
                all_articles, analysis_goal=goal, use_full_text=True,
            )
            _apply_tags_to_articles_sync(db, all_articles, tags)

            if tagging_job:
                tagging_job.source_count = len(all_articles)
                complete_analysis_job_sync(
                    db, tagging_job,
                    analyzed_count=len(all_articles),
                    token_usage=tag_token_usage,
                )
            else:
                db.flush()

            tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0, "wechat_mp": 0}
            for a in all_articles:
                tier = a.source_tier or "tier3"
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

            relevant_count = sum(
                1 for a in all_articles if a.relevance in ("high", "medium")
            )

            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            task.articles_count = len(all_articles)
            task.analysis_result = {
                "meta": {
                    "keywords": task.keywords,
                    "articles_total": len(all_articles),
                    "articles_crawled": articles_crawled,
                    "articles_analyzed": relevant_count,
                    "source_tier_distribution": tier_counts,
                    "channel_raw_counts": raw_counts,
                },
            }
            db.commit()

            logger.info(
                "NewsTask %d: collect completed, %d articles, %d crawled",
                task_id, len(all_articles), articles_crawled,
            )

        except Exception as e:
            logger.error("NewsTask %d: collect failed: %s", task_id, e, exc_info=True)
            db.rollback()
            # 在新事务里写入失败状态
            with SyncSessionLocal() as db2:
                task2 = db2.get(NewsTask, task_id)
                if task2:
                    task2.status = "failed"
                    task2.completed_at = datetime.now(timezone.utc)
                    task2.error_message = str(e)
                if tagging_job_id:
                    tj = db2.get(AnalysisJob, tagging_job_id)
                    if tj and tj.status == "running":
                        complete_analysis_job_sync(db2, tj, error_message=str(e))
                db2.commit()
