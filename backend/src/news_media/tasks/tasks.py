"""新闻媒体 Celery 任务（同步版）

将新闻全量采集（爬取 + 逐篇标注）转为同步 Celery 任务，
对齐社媒分析模块的架构：使用 SyncSessionLocal + gevent monkey-patch，
避免 asyncio event loop 与 gevent greenlet 之间的竞态（async_engine.dispose
在多 Celery 任务并发下会导致 asyncpg 连接池损坏，greenlet 永久卡住）。

insight 分析由切片（NewsSlice）按需触发，不在采集阶段执行。
"""

import logging
import time
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
            logger.error(
                "NewsTask %d: probe celery failed: %s", task_id, exc, exc_info=True
            )
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
        _compute_task_stats,
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
                db,
                task,
                max_results=40,
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
                        "articles_crawled": 0,
                        "channel_raw_counts": raw_counts,
                        **_compute_task_stats([]),
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
                    db,
                    tagging_job,
                    analyzed_count=len(all_articles),
                    token_usage=tag_token_usage,
                )
            else:
                db.flush()

            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            task.articles_count = len(all_articles)
            task.analysis_result = {
                "meta": {
                    "keywords": task.keywords,
                    "articles_crawled": articles_crawled,
                    "channel_raw_counts": raw_counts,
                    **_compute_task_stats(all_articles),
                },
            }
            db.commit()

            logger.info(
                "NewsTask %d: collect completed, %d articles, %d crawled",
                task_id,
                len(all_articles),
                articles_crawled,
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
) -> None:
    """运行 NewsSlice LLM 阶段（Pass 1 → derived → Pass 2，sync 版本）。

    前置：调用方已在主事务里跑过 `initialize_slice`，切片行带 subject/competitors
    列 + result_data.descriptive，status=analyzing。本任务从切片列直接读配置，
    重算 descriptive 后跑 LLM 阶段，把 LLM 产出键 merge 进 result_data。
    """
    from src.database import SyncSessionLocal
    from src.jobs.factory import (
        complete_analysis_job_sync,
        create_analysis_job_sync,
    )
    from src.jobs.models import AnalysisJob, AnalysisType
    from src.llm.chains.news.pass1_chain import (
        create_pass1_chain,
        format_articles_for_pass1,
    )
    from src.llm.chains.news.pass2_chain import (
        create_pass2_chain,
        format_entities_for_pass2,
        format_events_for_pass2,
        format_quotes_for_pass2,
    )
    from src.news_media.analysis.models import NewsSlice
    from src.llm.utils import extract_token_usage, merge_token_usage_stats
    from src.news_media.analysis.service import (
        _articles_for_llm,
        _build_stats_summary,
        _compute_derived,
        _compute_descriptive,
        _dedupe_and_filter,
        _parse_pass1_output,
        _parse_pass2_output,
    )
    from src.news_media.tasks.models import NewsArticle

    with SyncSessionLocal() as db:
        slice_obj = db.get(NewsSlice, slice_id)
        if not slice_obj:
            logger.error("NewsSlice %d not found, aborting insight", slice_id)
            return

        subject = slice_obj.subject or ""
        competitors = list(slice_obj.competitors or [])

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

            filtered, url_to_task_ids = _dedupe_and_filter(all_articles)
            job.source_count = len(filtered)

            descriptive = _compute_descriptive(filtered, url_to_task_ids)

            if not filtered:
                # initialize_slice 已置 completed；本路径理论上不会进来。兜底 merge 下。
                merged = dict(slice_obj.result_data or {})
                merged["descriptive"] = descriptive
                slice_obj.result_data = merged
                slice_obj.stats = _build_stats_summary(descriptive, entities=[])
                slice_obj.status = "completed"
                complete_analysis_job_sync(db, job, analyzed_count=0)
                logger.info(
                    "NewsSlice %d: no valid articles, marked completed", slice_id
                )
                return

            goal = analysis_goal or slice_obj.name

            # Step 2：Pass 1 LLM（sync）
            pass1_chain = create_pass1_chain()
            pass1_input_articles = _articles_for_llm(filtered)
            pass1_start = time.time()
            pass1_response = pass1_chain.invoke(
                {
                    "analysis_goal": goal,
                    "subject": subject,
                    "competitors": ", ".join(competitors) or "（未指定）",
                    "article_count": len(filtered),
                    "articles_content": format_articles_for_pass1(pass1_input_articles),
                }
            )
            pass1_token_usage = extract_token_usage(
                pass1_response,
                duration_seconds=time.time() - pass1_start,
            )
            pass1_parsed = _parse_pass1_output(pass1_response.content)

            # Step 3：派生层
            derived = _compute_derived(
                pass1_parsed,
                filtered,
                url_to_task_ids,
                subject=subject,
                competitors=competitors,
            )

            # Step 4：Pass 2 LLM（sync，失败容错）
            page_synthesis: dict = {}
            pass2_token_usage: dict | None = None
            try:
                pass2_chain = create_pass2_chain()
                article_titles_by_id = {a.id: a.title for a in filtered}
                pass2_start = time.time()
                pass2_response = pass2_chain.invoke(
                    {
                        "analysis_goal": goal,
                        "subject": subject or "（独立监测，无指定主体）",
                        "articles_filtered": descriptive.get("articles_filtered"),
                        "source_tier_dist": descriptive.get("source_tier_distribution"),
                        "search_source_dist": descriptive.get(
                            "search_source_distribution"
                        ),
                        "article_type_dist": descriptive.get(
                            "article_type_distribution"
                        ),
                        "sentiment_dist": descriptive.get("sentiment_distribution"),
                        "sentiment_overall": descriptive.get("sentiment_overall"),
                        "sentiment_by_tier": descriptive.get("sentiment_by_tier"),
                        "entities_block": format_entities_for_pass2(
                            derived.get("entities") or []
                        ),
                        "quotes_block": format_quotes_for_pass2(
                            derived.get("quotes") or []
                        ),
                        "events_block": format_events_for_pass2(
                            derived.get("event_clusters") or [],
                            article_titles_by_id,
                        ),
                    }
                )
                pass2_token_usage = extract_token_usage(
                    pass2_response,
                    duration_seconds=time.time() - pass2_start,
                )
                page_synthesis = _parse_pass2_output(pass2_response.content)
            except Exception as e:
                logger.warning("NewsSlice %d Pass 2 failed (页面降级): %s", slice_id, e)

            # Merge：保留已有 result_data 键，覆写 descriptive 与 LLM 产出键。
            # subject/competitors 不在 result_data，无需保护——它们是切片表列。
            merged = dict(slice_obj.result_data or {})
            merged["descriptive"] = descriptive
            merged.update(derived)
            merged["page_synthesis"] = page_synthesis
            slice_obj.result_data = merged
            slice_obj.stats = _build_stats_summary(descriptive, derived["entities"])
            slice_obj.status = "completed"

            # 用 merge_token_usage_stats（处理 {summary, call_details} 嵌套 schema）
            # 累加 pass1 + pass2 调用，前端读到 total_calls=2 与累计成本。
            token_usage = merge_token_usage_stats(pass1_token_usage, pass2_token_usage)
            complete_analysis_job_sync(
                db,
                job,
                analyzed_count=len(filtered),
                token_usage=token_usage,
            )
            logger.info(
                "NewsSlice %d analysis completed: %d articles", slice_id, len(filtered)
            )

        except Exception as e:
            logger.error("NewsSlice %d analysis failed: %s", slice_id, e, exc_info=True)
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
