"""新闻媒体 Celery 任务

将新闻全量采集（爬取 + 逐篇标注）转为异步 Celery 任务，
���持与社媒��块一致的架构：router 创建 AnalysisJob �� Celery 执行 → 更新 job 状态。
insight 分析由切片（NewsSlice）按需触发，不在采集阶段执行。
"""

import asyncio
import logging
from datetime import datetime, timezone

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 gevent threadpool 的真实 OS 线程中运行协程。

    gevent monkey-patch 后 worker greenlet 无法直接使用 asyncio.run()；
    通过 gevent threadpool 在真实 OS 线程中调用，避免
    "cannot be called from a running event loop" 错误。
    """
    from gevent import get_hub
    return get_hub().threadpool.apply(asyncio.run, (coro,))


@celery_app.task(
    name="news_media.run_probe",
    bind=True,
    max_retries=0,
)
def run_news_probe_task(self, task_id: int) -> None:
    """执行新闻探测 Celery 任务（仅搜索 + 落库，无 LLM）"""
    _run_async(_async_run_probe(task_id=task_id))


async def _async_run_probe(task_id: int) -> None:
    """异步执行新闻探测（供 Celery task 调用）"""
    from src.database import AsyncSessionLocal, async_engine
    from src.news_media.tasks.models import NewsTask
    from src.news_media.tasks.service import execute_news_probe

    # 见 _async_run_collect 中同类注释：gevent 下新 loop 需拿到干净连接
    await async_engine.dispose()

    async with AsyncSessionLocal() as db:
        task = await db.get(NewsTask, task_id)
        if not task:
            logger.error("NewsTask %d not found, aborting probe", task_id)
            return
        try:
            await execute_news_probe(db, task)
            await db.commit()
        except Exception as exc:
            logger.error("NewsTask %d: probe celery failed: %s", task_id, exc, exc_info=True)
            await db.rollback()


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
    """执行新闻全量采集 Celery 任务

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
    _run_async(_async_run_collect(
        task_id=task_id,
        tagging_job_id=tagging_job_id,
        analysis_goal=analysis_goal,
    ))


async def _async_run_collect(
    task_id: int,
    tagging_job_id: int | None,
    analysis_goal: str,
) -> None:
    """异步执行新闻全量采集流水线（供 Celery task 调用）

    流程：搜索 → 存文章 → 抓全文 → 逐篇标注 → 更新统计。
    insight 分析由 NewsSlice 按需触发。
    """
    from src.database import AsyncSessionLocal, async_engine
    from src.news_media.tasks.models import NewsTask
    from src.jobs.models import AnalysisJob

    # Celery gevent worker 下每个任务用 asyncio.run() 新建事件循环，
    # async_engine 池中残留的 asyncpg 连接绑定的是旧 loop，会触发
    # "attached to a different loop"。先 dispose 让新 loop 拿到干净连接。
    await async_engine.dispose()

    async with AsyncSessionLocal() as db:
        task = await db.get(NewsTask, task_id)
        if not task:
            logger.error("NewsTask %d not found, aborting", task_id)
            return

        tagging_job = await db.get(AnalysisJob, tagging_job_id) if tagging_job_id else None

        goal = analysis_goal or task.keywords

        try:
            from src.jobs.factory import start_analysis_job_async, complete_analysis_job_async

            task.status = "running"
            task.started_at = datetime.now(timezone.utc)
            if tagging_job:
                await start_analysis_job_async(db, tagging_job)
            else:
                await db.commit()

            from src.news_media.tasks.service import _resolve_channels, _search_and_store_articles

            articles = await _search_and_store_articles(
                db, task, max_results=20, channels=_resolve_channels(task)
            )

            if not articles:
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                task.articles_count = 0
                task.analysis_result = {"meta": {"keywords": task.keywords, "articles_total": 0}}
                if tagging_job:
                    await complete_analysis_job_async(db, tagging_job, analyzed_count=0)
                else:
                    await db.commit()
                return

            from src.news_media.tasks.article_crawler import crawl_articles

            urls = [a.url for a in articles]
            crawl_results = await crawl_articles(urls)

            articles_crawled = 0
            from src.news_media.tasks import crud
            for article in articles:
                full_text = crawl_results.get(article.url)
                if full_text:
                    await crud.update_article(db, article, {"full_text": full_text})
                    articles_crawled += 1
            await db.flush()

            from src.news_media.tasks.service import _tag_articles_batch, _apply_tags_to_articles

            all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=200)

            tags, tag_token_usage = await _tag_articles_batch(all_articles, analysis_goal=goal, use_full_text=True)
            await _apply_tags_to_articles(db, all_articles, tags)

            if tagging_job:
                tagging_job.source_count = len(all_articles)
                await complete_analysis_job_async(
                    db, tagging_job,
                    analyzed_count=len(all_articles),
                    token_usage=tag_token_usage,
                )
            else:
                await db.flush()

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
                },
            }
            await db.commit()

            logger.info(
                "NewsTask %d: collect completed, %d articles, %d crawled",
                task_id, len(all_articles), articles_crawled,
            )

        except Exception as e:
            logger.error("NewsTask %d: collect failed: %s", task_id, e, exc_info=True)
            task.status = "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.error_message = str(e)
            if tagging_job and tagging_job.status == "running":
                await complete_analysis_job_async(
                    db, tagging_job, error_message=str(e),
                )
            else:
                await db.commit()
