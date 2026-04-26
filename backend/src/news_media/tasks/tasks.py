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
    subject: str = "",
    competitors: list[str] | None = None,
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
        subject: 研究主体（策略场景传 brand_brief.subject；独立场景传空）
        competitors: 已知竞品列表（策略场景传 slice_blueprint union；独立场景传空）
            供 tagging_chain role 硬绑定使用
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
                max_results=30,
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
                all_articles,
                analysis_goal=goal,
                use_full_text=True,
                subject=subject,
                competitors=competitors,
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


@celery_app.task(
    name="news_media.run_news_slice_insight",
    bind=True,
    max_retries=0,
)
def run_news_slice_insight_task(
    self,
    slice_id: int,
    user_id: int,
    analysis_goal: str = "",
    subject: str = "",
    competitors: list[str] | None = None,
) -> None:
    """运行 NewsSlice insight 分析（同步版，策略场景专用）

    策略场景下 _create_auto_slices 创建 NewsSlice 行（status=pending）后，
    commit 主事务再异步派发本任务跑 insight。这样避免长事务（LLM ~90s）
    持有 INSERT 不 commit，导致 APScheduler / 轮询读不到该行重复建切片。

    独立监测场景仍走 news_media.analysis.service.run_slice_analysis（async）。
    """
    from src.database import SyncSessionLocal
    from src.jobs.factory import (
        complete_analysis_job_sync,
        create_analysis_job_sync,
    )
    from src.jobs.models import AnalysisJob, AnalysisType
    from src.news_media.analysis.models import NewsSlice
    from src.news_media.analysis.service import _compute_stats
    from src.news_media.tasks.models import NewsArticle
    from src.news_media.tasks.service import _run_insight_analysis_sync

    with SyncSessionLocal() as db:
        slice_obj = db.get(NewsSlice, slice_id)
        if not slice_obj:
            logger.error("NewsSlice %d not found, aborting insight", slice_id)
            return

        slice_obj.status = "analyzing"
        slice_obj.error_message = None
        db.commit()

        job = create_analysis_job_sync(
            db=db,
            news_monitor_id=slice_obj.monitor_id,
            user_id=user_id,
            analysis_type=AnalysisType.NEWS_INSIGHT.value,
            source_count=0,
            analysis_config={"slice_id": slice_id, "via": "strategy"},
            status="running",
        )

        try:
            stmt = (
                select(NewsArticle)
                .where(NewsArticle.task_id.in_(slice_obj.included_task_ids))
                .order_by(NewsArticle.published_at.desc().nulls_last())
            )
            all_articles = list(db.execute(stmt).scalars().all())

            seen_urls: set[str] = set()
            deduped: list = []
            for a in all_articles:
                if a.url not in seen_urls:
                    seen_urls.add(a.url)
                    deduped.append(a)
            filtered = [a for a in deduped if a.relevance != "low"]

            slice_obj.stats = _compute_stats(filtered)
            job.source_count = len(filtered)

            if not filtered:
                slice_obj.result_data = {"meta": {"articles_total": 0}}
                slice_obj.status = "completed"
                complete_analysis_job_sync(db, job, analyzed_count=0)
                logger.info("NewsSlice %d: no valid articles, marked completed", slice_id)
                return

            goal = analysis_goal or slice_obj.name
            insights, token_usage = _run_insight_analysis_sync(
                filtered,
                analysis_goal=goal,
                subject=subject or "",
                competitors=competitors or [],
            )

            if isinstance(insights, dict) and "error" not in insights:
                slice_obj.result_data = insights
            else:
                slice_obj.result_data = {"meta": slice_obj.stats, "error": str(insights)}
            slice_obj.status = "completed"
            complete_analysis_job_sync(
                db, job,
                analyzed_count=len(filtered),
                token_usage=token_usage,
            )
            logger.info("NewsSlice %d insight completed: %d articles", slice_id, len(filtered))

        except Exception as e:
            logger.error("NewsSlice %d insight failed: %s", slice_id, e, exc_info=True)
            db.rollback()
            with SyncSessionLocal() as db2:
                s2 = db2.get(NewsSlice, slice_id)
                if s2:
                    s2.status = "failed"
                    s2.error_message = str(e)[:1000]
                j2 = db2.get(AnalysisJob, job.id)
                if j2 and j2.status == "running":
                    complete_analysis_job_sync(db2, j2, error_message=str(e)[:500])
                db2.commit()
