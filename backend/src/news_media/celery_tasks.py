"""新闻媒体 Celery 任务

将新闻全量采集（爬取 + 逐篇标注 + 整体洞察）转为异步 Celery 任务，
保持与社媒模块一致的架构：router 创建 AnalysisJob → Celery 执行 → 更新 job 状态。
"""

import asyncio
import logging
from datetime import datetime, timezone

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="news_media.run_collect",
    bind=True,
    max_retries=0,
)
def run_news_collect_task(
    self,
    task_id: int,
    tagging_job_id: int,
    insight_job_id: int,
    analysis_goal: str = "",
    subject: str = "",
) -> None:
    """执行新闻全量采集 Celery 任务

    流程：
    1. 双渠道搜索 + 存文章
    2. Crawl4AI 抓全文
    3. 逐篇标注（NEWS_TAGGING job）
    4. 整体洞察（NEWS_INSIGHT job）
    5. 更新 NewsTask 状态

    Args:
        task_id: NewsTask ID
        tagging_job_id: 逐篇标注的 AnalysisJob ID
        insight_job_id: 整体洞察的 AnalysisJob ID
        analysis_goal: 分析目标（可选，默认用任务关键词）
        subject: 分析主体（可选，默认用任务关键词）
    """
    asyncio.run(_async_run_collect(
        task_id=task_id,
        tagging_job_id=tagging_job_id,
        insight_job_id=insight_job_id,
        analysis_goal=analysis_goal,
        subject=subject,
    ))


async def _async_run_collect(
    task_id: int,
    tagging_job_id: int,
    insight_job_id: int,
    analysis_goal: str,
    subject: str,
) -> None:
    """异步执行新闻全量采集流水线（供 Celery task 调用）"""
    from src.database import AsyncSessionLocal
    from src.news_media.models import NewsTask
    from src.analysis.models import AnalysisJob
    from src.langchain import extract_token_usage

    async with AsyncSessionLocal() as db:
        task = await db.get(NewsTask, task_id)
        if not task:
            logger.error("NewsTask %d not found, aborting", task_id)
            return

        tagging_job = await db.get(AnalysisJob, tagging_job_id)
        insight_job = await db.get(AnalysisJob, insight_job_id)

        goal = analysis_goal or task.keywords
        subj = subject or task.keywords

        try:
            task.status = "running"
            if tagging_job:
                tagging_job.status = "processing"
                tagging_job.started_at = datetime.now(timezone.utc)
            await db.commit()

            # Step 1-2: 搜索 + 爬取全文（无 LLM）
            from src.news_media.service import _search_and_store_articles

            articles = await _search_and_store_articles(
                db, task, max_results=50, channels=("baidu", "duckduckgo")
            )

            if not articles:
                task.status = "completed"
                task.articles_count = 0
                task.analysis_result = {"meta": {"keywords": task.keywords, "articles_total": 0}}
                if tagging_job:
                    tagging_job.status = "completed"
                    tagging_job.completed_at = datetime.now(timezone.utc)
                    tagging_job.analyzed_count = 0
                if insight_job:
                    insight_job.status = "completed"
                    insight_job.completed_at = datetime.now(timezone.utc)
                    insight_job.analyzed_count = 0
                await db.commit()
                return

            from src.news_media.article_crawler import crawl_articles

            urls = [a.url for a in articles]
            crawl_results = await crawl_articles(urls)

            articles_crawled = 0
            from src.news_media import crud
            for article in articles:
                full_text = crawl_results.get(article.url)
                if full_text:
                    await crud.update_article(db, article, {"full_text": full_text})
                    articles_crawled += 1
            await db.flush()

            # Step 3: 逐篇标注（NEWS_TAGGING）
            from src.news_media.service import _tag_articles_batch, _apply_tags_to_articles

            all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=200)
            tag_start = datetime.now(timezone.utc)

            tags = await _tag_articles_batch(all_articles, analysis_goal=goal, use_full_text=True)
            await _apply_tags_to_articles(db, all_articles, tags)

            tag_duration = (datetime.now(timezone.utc) - tag_start).total_seconds()

            if tagging_job:
                tagging_job.status = "completed"
                tagging_job.completed_at = datetime.now(timezone.utc)
                tagging_job.analyzed_count = len(all_articles)
                tagging_job.processing_time = int(tag_duration)
                tagging_job.source_count = len(all_articles)

            await db.flush()

            # Step 4: 整体洞察（NEWS_INSIGHT）
            if insight_job:
                insight_job.status = "processing"
                insight_job.started_at = datetime.now(timezone.utc)
                insight_job.source_count = len(all_articles)
            await db.flush()

            all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=200)
            insight_start = datetime.now(timezone.utc)

            from src.news_media.service import _run_insight_analysis
            insights = await _run_insight_analysis(all_articles, analysis_goal=goal, subject=subj)

            insight_duration = (datetime.now(timezone.utc) - insight_start).total_seconds()

            if insight_job:
                insight_job.status = "completed"
                insight_job.completed_at = datetime.now(timezone.utc)
                insight_job.analyzed_count = 1
                insight_job.processing_time = int(insight_duration)

            # 更新 NewsTask
            tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
            for a in all_articles:
                tier = a.source_tier or "tier3"
                tier_counts[tier] = tier_counts.get(tier, 0) + 1

            relevant_count = sum(
                1 for a in all_articles if a.relevance in ("high", "medium")
            )

            analysis_result = {
                "meta": {
                    "keywords": task.keywords,
                    "articles_total": len(all_articles),
                    "articles_crawled": articles_crawled,
                    "articles_analyzed": relevant_count,
                    "source_tier_distribution": tier_counts,
                },
            }
            if isinstance(insights, dict) and "error" not in insights:
                analysis_result.update(insights)

            task.status = "completed"
            task.articles_count = len(all_articles)
            task.analysis_result = analysis_result
            await db.commit()

            logger.info(
                "NewsTask %d: collect completed, %d articles, %d crawled",
                task_id, len(all_articles), articles_crawled,
            )

        except Exception as e:
            logger.error("NewsTask %d: collect failed: %s", task_id, e, exc_info=True)
            task.status = "failed"
            task.error_message = str(e)
            if tagging_job and tagging_job.status == "processing":
                tagging_job.status = "failed"
                tagging_job.error_message = str(e)
                tagging_job.completed_at = datetime.now(timezone.utc)
            if insight_job and insight_job.status == "processing":
                insight_job.status = "failed"
                insight_job.error_message = str(e)
                insight_job.completed_at = datetime.now(timezone.utc)
            await db.commit()
