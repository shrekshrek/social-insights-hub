"""新闻监测项目服务层"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.monitors import crud
from src.news_media.monitors.models import NewsMonitor
from src.news_media.monitors.schemas import NewsMonitorCreate, NewsMonitorUpdate

logger = logging.getLogger(__name__)


async def create_news_monitor(
    db: AsyncSession, data: NewsMonitorCreate, user_id: int
) -> NewsMonitor:
    """创建新闻监测项目"""
    existing = await crud.get_monitor_by_name(db, data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"监测项目名称 '{data.name}' 已存在",
        )
    monitor_data = data.model_dump(exclude={"participant_ids"})
    monitor = await crud.create_monitor(db, monitor_data, user_id, participant_ids=data.participant_ids)
    await db.commit()
    await db.refresh(monitor, ["owner", "participants"])
    return monitor


async def get_news_monitors(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    owner_id: int | None = None,
    participant_id: int | None = None,
    search: str | None = None,
) -> tuple[list[NewsMonitor], int]:
    """获取新闻监测项目列表"""
    skip = (page - 1) * page_size
    return await crud.get_monitors(
        db, skip=skip, limit=page_size,
        owner_id=owner_id, participant_id=participant_id, search=search,
    )


async def get_news_monitor(db: AsyncSession, monitor_id: int) -> NewsMonitor | None:
    """获取单个新闻监测项目"""
    return await crud.get_monitor_by_id(db, monitor_id, load_relations=True)


async def update_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, data: NewsMonitorUpdate
) -> NewsMonitor:
    """更新新闻监测项目"""
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != monitor.name:
        existing = await crud.get_monitor_by_name(db, update_data["name"])
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"监测项目名称 '{update_data['name']}' 已存在",
            )
    monitor = await crud.update_monitor(db, monitor, update_data)
    await db.commit()
    await db.refresh(monitor, ["owner", "participants"])
    return monitor


async def delete_news_monitor(db: AsyncSession, monitor: NewsMonitor) -> None:
    """删除新闻监测项目"""
    await crud.delete_monitor(db, monitor)
    await db.commit()


async def add_participants_to_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_ids: list[int]
) -> NewsMonitor:
    """为新闻监测项目添加参与者（owner 不会被加入）"""
    if monitor.owner_id in user_ids:
        user_ids = [uid for uid in user_ids if uid != monitor.owner_id]
    if not user_ids:
        return monitor
    return await crud.add_participants_to_news_monitor(db, monitor, user_ids)


async def remove_participant_from_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_id: int
) -> NewsMonitor:
    """从新闻监测项目移除参与者"""
    if user_id == monitor.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除项目所有者",
        )
    if user_id not in {p.id for p in monitor.participants}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 {user_id} 不是该项目的参与者",
        )
    return await crud.remove_participant_from_news_monitor(db, monitor, user_id)


async def get_monitor_aggregated_stats(
    db: AsyncSession,
    monitor_id: int,
) -> dict:
    """统计聚合：从各 collect 任务的 analysis_result 合并统计，无 LLM 调用。

    返回：文章总数、相关文章数、情感分布、实体 Top10、来源分布。
    Monitor 无文章时返回全零结构。
    """
    from src.news_media.tasks.crud import get_articles_by_monitor

    articles = await get_articles_by_monitor(db, monitor_id, phase="collect")

    if not articles:
        return {
            "articles_total": 0,
            "articles_relevant": 0,
            "source_tier_distribution": {"tier1": 0, "tier2": 0, "tier3": 0},
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "sentiment_overall": None,
            "top_entities": [],
            "search_source_distribution": {"baidu": 0, "duckduckgo": 0},
        }

    relevant = [a for a in articles if a.relevance in ("high", "medium")]
    tier_counts: dict[str, int] = {"tier1": 0, "tier2": 0, "tier3": 0}
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    source_dist: dict[str, int] = {"baidu": 0, "duckduckgo": 0}
    sentiment_scores: list[float] = []
    entity_mentions: dict[str, int] = {}

    for a in articles:
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        src = getattr(a, "search_source", "baidu") or "baidu"
        source_dist[src] = source_dist.get(src, 0) + 1

    for a in relevant:
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
        "articles_relevant": len(relevant),
        "source_tier_distribution": tier_counts,
        "sentiment_distribution": sentiment_dist,
        "sentiment_overall": sentiment_overall,
        "top_entities": top_entities,
        "search_source_distribution": source_dist,
    }


async def run_monitor_narrative_aggregate(
    db: AsyncSession,
    monitor: NewsMonitor,
    analysis_goal: str = "",
    subject: str = "",
) -> dict:
    """叙事聚合：合并 monitor 下所有 collect 任务文章，跑一次 news_insight_chain。

    结果写入 monitor.aggregated_result 并 commit。
    无 completed collect 任务时抛 HTTPException 400。
    """
    from src.news_media.tasks.crud import get_articles_by_monitor
    from src.news_media.tasks.service import _run_insight_analysis

    articles = await get_articles_by_monitor(db, monitor.id, phase="collect")
    if not articles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该监测项目下没有已完成的全量采集任务，无法生成聚合报告",
        )

    goal = analysis_goal or monitor.name
    subj = subject or monitor.name
    insights = await _run_insight_analysis(articles, analysis_goal=goal, subject=subj)

    monitor.aggregated_result = insights
    await db.commit()
    await db.refresh(monitor)
    return insights
