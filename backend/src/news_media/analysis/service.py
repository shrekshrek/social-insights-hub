"""新闻切片 service 层

创建切片 → 合并文章 → URL 去重 → 低相关过滤 → 计算统计 → 运行 insight 分析
insight 分析通过 AnalysisJob 追踪 token/进度/状态。
"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.analysis import crud
from src.news_media.analysis.models import NewsSlice
from src.news_media.analysis.schemas import NewsSliceCreate

logger = logging.getLogger(__name__)


async def create_slice(
    db: AsyncSession,
    monitor_id: int,
    data: NewsSliceCreate,
    user_id: int,
) -> NewsSlice:
    """创建新闻切片并自动触发 insight 分析

    对齐社媒切片行为：创建即分析，无需手动触发。
    """
    from src.news_media.tasks.models import NewsTask

    # 校验所有 task 属于该 monitor 且是 completed collect
    for tid in data.included_task_ids:
        task = await db.get(NewsTask, tid)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务 {tid} 不存在",
            )
        if task.monitor_id != monitor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务 {tid} 不属于该监测项目",
            )
        if task.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"任务 {tid} 尚未完成采集",
            )

    slice_obj = await crud.create_news_slice(
        db,
        monitor_id=monitor_id,
        name=data.name,
        included_task_ids=data.included_task_ids,
        user_id=user_id,
    )

    # 创建即分析。独立监测场景 subject 传空（无明确研究主体），insight_chain 退化为
    # 全部实体归 context；若后续 UI 层扩展 NewsSliceCreate 允许用户指定 subject/competitors，
    # 在此传入即可（对齐社媒 MonitorSliceCreate 的设计）
    return await run_slice_analysis(
        db, slice_obj, user_id=user_id,
        analysis_goal=data.name, subject="", competitors=[],
    )


async def run_slice_analysis(
    db: AsyncSession,
    slice_obj: NewsSlice,
    user_id: int,
    analysis_goal: str = "",
    subject: str = "",
    competitors: list[str] | None = None,
) -> NewsSlice:
    """运行切片 insight 分析：合并文章 → 去重 → 筛选 → 统计 → insight chain

    subject / competitors: 供 insight_chain 做 role 硬绑定。独立监测场景默认空
    （LLM 退化为全部 context）；策略场景由 `_create_strategy_news_slice` 明确传入。

    创建 NEWS_INSIGHT AnalysisJob 追踪 token/耗时/状态。
    """
    from sqlalchemy import select

    from src.jobs.factory import complete_analysis_job_async, create_analysis_job_async
    from src.jobs.models import AnalysisType
    from src.news_media.tasks.models import NewsArticle, NewsTask

    slice_obj.status = "analyzing"
    slice_obj.error_message = None
    await db.commit()

    # 创建 NEWS_INSIGHT AnalysisJob
    job = await create_analysis_job_async(
        db=db,
        news_monitor_id=slice_obj.monitor_id,
        user_id=user_id,
        analysis_type=AnalysisType.NEWS_INSIGHT.value,
        source_count=0,
        analysis_config={"slice_id": slice_obj.id},
        status="running",
    )

    try:
        # 查询切片内所有任务的文章
        stmt = (
            select(NewsArticle)
            .join(NewsTask, NewsArticle.task_id == NewsTask.id)
            .where(
                NewsTask.id.in_(slice_obj.included_task_ids),
                NewsTask.status == "completed",
            )
            .order_by(NewsArticle.published_at.desc().nulls_last())
        )
        result = await db.execute(stmt)
        all_articles = list(result.scalars().all())

        # URL 去重
        seen_urls: set[str] = set()
        unique_articles = []
        for a in all_articles:
            if a.url not in seen_urls:
                seen_urls.add(a.url)
                unique_articles.append(a)

        # 过滤低相关
        filtered = [a for a in unique_articles if a.relevance != "low"]

        # 计算统计
        stats = _compute_stats(filtered)
        slice_obj.stats = stats
        job.source_count = len(filtered)

        if not filtered:
            slice_obj.status = "completed"
            slice_obj.result_data = {"meta": {"articles_total": 0}}
            await complete_analysis_job_async(db, job, analyzed_count=0)
            await db.refresh(slice_obj)
            return slice_obj

        # 运行 insight chain
        from src.news_media.tasks.service import _run_insight_analysis

        goal = analysis_goal or slice_obj.name
        # 独立切片场景 subject 传空时，insight_chain 退化为全部标 context；
        # 不再默认 fallback 到 slice_obj.name（避免切片名被错误当作品牌）
        subj = subject or ""
        comp_list = competitors or []
        insights, token_usage = await _run_insight_analysis(
            filtered,
            analysis_goal=goal,
            subject=subj,
            competitors=comp_list,
        )

        if isinstance(insights, dict) and "error" not in insights:
            slice_obj.result_data = insights
        else:
            slice_obj.result_data = {"meta": stats, "error": str(insights)}

        slice_obj.status = "completed"
        await complete_analysis_job_async(
            db, job, analyzed_count=1, token_usage=token_usage,
        )
        await db.refresh(slice_obj)
        return slice_obj

    except Exception as e:
        logger.error("NewsSlice %d analysis failed: %s", slice_obj.id, e, exc_info=True)
        slice_obj.status = "failed"
        slice_obj.error_message = str(e)[:1000]
        await complete_analysis_job_async(
            db, job, error_message=str(e)[:500],
        )
        await db.refresh(slice_obj)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"切片分析失败: {e}",
        ) from e


def _compute_stats(articles: list) -> dict:
    """从文章列表计算统计摘要"""
    tier_counts: dict[str, int] = {"tier1": 0, "tier2": 0, "tier3": 0, "wechat_mp": 0}
    # 初始化常规渠道为 0；历史文章若 search_source='bing'（下线前数据）会在循环中自动补键，
    # source_dist.get(src, 0) + 1 保证不丢旧数据，只是不把 bing 列成默认展示位。
    source_dist: dict[str, int] = {"baidu": 0, "sogou": 0, "wechat_mp": 0}
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    sentiment_scores: list[float] = []
    entity_mentions: dict[str, int] = {}

    for a in articles:
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        src = getattr(a, "search_source", "baidu") or "baidu"
        source_dist[src] = source_dist.get(src, 0) + 1

        if a.sentiment is not None:
            sentiment_scores.append(a.sentiment)
            if a.sentiment > 0:
                sentiment_dist["positive"] += 1
            elif a.sentiment < 0:
                sentiment_dist["negative"] += 1
            else:
                sentiment_dist["neutral"] += 1

        for ent in (a.mentioned_entities or []):
            name = ent.get("name", "")
            if name:
                entity_mentions[name] = entity_mentions.get(name, 0) + 1

    sentiment_overall = (
        round(sum(sentiment_scores) / len(sentiment_scores), 3)
        if sentiment_scores else None
    )
    top_entities = sorted(
        [{"name": k, "mention_count": v} for k, v in entity_mentions.items()],
        key=lambda x: x["mention_count"],
        reverse=True,
    )[:10]

    return {
        "articles_total": len(articles),
        "source_tier_distribution": tier_counts,
        "search_source_distribution": source_dist,
        "sentiment_distribution": sentiment_dist,
        "sentiment_overall": sentiment_overall,
        "top_entities": top_entities,
    }
