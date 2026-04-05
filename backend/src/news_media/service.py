"""新闻媒体服务层"""

import json
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media import crud
from src.news_media.models import NewsMonitor, NewsTask
from src.news_media.schemas import NewsMonitorCreate, NewsMonitorUpdate, NewsTaskCreate

logger = logging.getLogger(__name__)

# 逐篇标注的批次大小
_TAGGING_BATCH_SIZE = 5


# ==================== NewsMonitor Service ====================


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


# ==================== NewsTask Service ====================


async def create_news_task(
    db: AsyncSession,
    monitor_id: int,
    data: NewsTaskCreate,
    user_id: int,
    strategy_id: int | None = None,
    phase: str | None = None,
) -> NewsTask:
    """创建新闻任务"""
    monitor = await crud.get_monitor_by_id(db, monitor_id, load_relations=False)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"监测项目 {monitor_id} 不存在",
        )
    task_data = {
        "name": data.name,
        "monitor_id": monitor_id,
        "strategy_id": strategy_id,
        "keywords": data.keywords,
        "phase": phase,
        "search_params": data.search_params,
        "created_by": user_id,
    }
    task = await crud.create_task(db, task_data)
    await db.commit()
    await db.refresh(task, ["monitor", "creator"])
    return task


async def get_news_tasks(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    monitor_id: int | None = None,
    status_filter: str | None = None,
    phase: str | None = None,
    search: str | None = None,
) -> tuple[list[NewsTask], int]:
    """获取新闻任务列表"""
    skip = (page - 1) * page_size
    return await crud.get_tasks(
        db, skip=skip, limit=page_size,
        monitor_id=monitor_id, status=status_filter,
        phase=phase, search=search,
    )


async def get_news_task(db: AsyncSession, task_id: int) -> NewsTask | None:
    """获取单个新闻任务"""
    return await crud.get_task_by_id(db, task_id, load_relations=True)


async def get_news_tasks_by_strategy(
    db: AsyncSession, strategy_id: int, phase: str | None = None
) -> list[NewsTask]:
    """查询策略的新闻任务"""
    return await crud.get_tasks_by_strategy(db, strategy_id, phase=phase)


async def delete_news_task(db: AsyncSession, task: NewsTask) -> None:
    """删除新闻任务"""
    await crud.delete_task(db, task)
    await db.commit()


# ==================== Internal Helpers ====================


def _parse_llm_json(content: str) -> list | dict:
    """从 LLM 响应��提取 JSON（兼容 markdown code block 包裹）"""
    # 尝试提取 JSON 数组
    array_match = re.search(r"\[[\s\S]*\]", content)
    if array_match:
        return json.loads(array_match.group())
    # 尝试提取 JSON 对象
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        return json.loads(obj_match.group())
    return json.loads(content)


async def _search_and_store_articles(
    db: AsyncSession,
    task: NewsTask,
    max_results: int = 10,
    channels: tuple = ("baidu",),
) -> list:
    """双渠道搜索 + 存入 NewsArticle（去重），返回新建的文章列表"""
    from src.news_media.news_search.aggregator import search_news

    search_results = await search_news(
        query=task.keywords,
        max_results=max_results,
        channels=list(channels),
    )
    if not search_results:
        return []

    # 按 URL 去重（排除已存在的）
    urls = [r["url"] for r in search_results]
    existing = await crud.get_articles_by_urls(db, urls)
    existing_urls = {a.url for a in existing}

    new_articles_data = [
        {
            "task_id": task.id,
            "url": r["url"],
            "title": r["title"],
            "snippet": r.get("snippet"),
            "source_name": r["source_name"],
            "source_tier": r["source_tier"],
            "search_source": r.get("search_source", "baidu"),
            "published_at": r.get("published_at"),
            "image_url": r.get("image_url"),
            "raw_data": r.get("raw_data"),
        }
        for r in search_results
        if r["url"] not in existing_urls
    ]

    if not new_articles_data:
        return []

    articles = await crud.bulk_create_articles(db, new_articles_data)
    await db.flush()
    return articles


async def _tag_articles_batch(
    articles: list,
    analysis_goal: str,
    use_full_text: bool = False,
) -> list[dict]:
    """逐篇轻量标注（批量，_TAGGING_BATCH_SIZE 篇一组）"""
    from src.langchain.chains.news_tagging_chain import (
        create_news_tagging_chain,
        format_articles_for_tagging,
    )

    chain = create_news_tagging_chain()
    all_tags: list[dict] = []

    for i in range(0, len(articles), _TAGGING_BATCH_SIZE):
        batch = articles[i:i + _TAGGING_BATCH_SIZE]
        batch_dicts = [
            {
                "title": a.title,
                "source_name": a.source_name,
                "snippet": a.snippet,
                "full_text": a.full_text if use_full_text else None,
            }
            for a in batch
        ]

        articles_content = format_articles_for_tagging(batch_dicts, use_full_text=use_full_text)
        response = await chain.ainvoke({
            "analysis_goal": analysis_goal,
            "article_count": len(batch),
            "articles_content": articles_content,
        })

        try:
            tags = _parse_llm_json(response.content)
            if isinstance(tags, list):
                all_tags.extend(tags)
            else:
                logger.warning("news_tagging_chain returned non-list: %s", type(tags))
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse tagging response: %s", e)

    return all_tags


async def _apply_tags_to_articles(
    db: AsyncSession,
    articles: list,
    tags: list[dict],
) -> None:
    """将标注结果写回 NewsArticle"""
    for tag in tags:
        idx = tag.get("article_index")
        if idx is None or idx >= len(articles):
            continue
        article = articles[idx]
        update_data = {}
        if "relevance" in tag:
            update_data["relevance"] = tag["relevance"]
        if "sentiment" in tag:
            update_data["sentiment"] = tag["sentiment"]
        if "article_type" in tag:
            update_data["article_type"] = tag["article_type"]
        if "mentioned_entities" in tag:
            update_data["mentioned_entities"] = tag["mentioned_entities"]
        if "key_quotes" in tag:
            update_data["key_quotes"] = tag["key_quotes"]
        if "summary" in tag:
            update_data["summary"] = tag["summary"]
        if update_data:
            await crud.update_article(db, article, update_data)
    await db.flush()


async def _run_insight_analysis(
    articles: list,
    analysis_goal: str,
    subject: str,
) -> dict:
    """整体分析（一次 LLM 调用），返回结构化洞察"""
    from src.langchain.chains.news_insight_chain import (
        create_news_insight_chain,
        format_tagged_articles_for_insight,
    )

    # 只纳入 relevance=high/medium 的文章
    relevant = [
        a for a in articles
        if a.relevance in ("high", "medium") or a.relevance is None
    ]

    article_dicts = [
        {
            "title": a.title,
            "source_name": a.source_name,
            "source_tier": a.source_tier,
            "published_at": str(a.published_at) if a.published_at else "未知",
            "relevance": a.relevance,
            "sentiment": a.sentiment,
            "article_type": a.article_type,
            "mentioned_entities": a.mentioned_entities,
            "key_quotes": a.key_quotes,
            "summary": a.summary,
        }
        for a in relevant
    ]

    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
    for a in relevant:
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    tagged_content = format_tagged_articles_for_insight(article_dicts)

    chain = create_news_insight_chain()
    response = await chain.ainvoke({
        "analysis_goal": analysis_goal,
        "subject": subject,
        "article_count": len(relevant),
        "tagged_articles": tagged_content,
        "tier1_count": tier_counts["tier1"],
        "tier2_count": tier_counts["tier2"],
        "tier3_count": tier_counts["tier3"],
    })

    try:
        return _parse_llm_json(response.content)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse insight response: %s", e)
        return {"error": str(e)}


# ==================== Monitor 聚合分析 ====================


async def get_monitor_aggregated_stats(
    db: AsyncSession,
    monitor_id: int,
) -> dict:
    """统计聚合：从各 collect 任务的 analysis_result 合并统计，无 LLM 调用。

    返回：文章总数、相关文章数、情感分布、实体 Top10、来源分布。
    Monitor 无文章时返回全零结构。
    """
    articles = await crud.get_articles_by_monitor(db, monitor_id, phase="collect")

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

    # 基础统计
    relevant = [a for a in articles if a.relevance in ("high", "medium")]
    tier_counts: dict[str, int] = {"tier1": 0, "tier2": 0, "tier3": 0}
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    source_dist: dict[str, int] = {"baidu": 0, "duckduckgo": 0}
    sentiment_scores: list[float] = []
    entity_mentions: dict[str, int] = {}

    for a in articles:
        # 来源分布
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # 搜索渠道分布
        src = getattr(a, "search_source", "baidu") or "baidu"
        source_dist[src] = source_dist.get(src, 0) + 1

    for a in relevant:
        # 情感
        if a.sentiment is not None:
            sentiment_scores.append(a.sentiment)
            if a.sentiment > 0:
                sentiment_dist["positive"] += 1
            elif a.sentiment < 0:
                sentiment_dist["negative"] += 1
            else:
                sentiment_dist["neutral"] += 1

        # 实体统计
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
    articles = await crud.get_articles_by_monitor(db, monitor.id, phase="collect")
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


# ==================== Task Execution ====================


async def execute_news_probe(
    db: AsyncSession,
    task: NewsTask,
    analysis_goal: str = "",
) -> None:
    """执行新闻探测：百度新闻搜索 → 存 NewsArticle → 逐篇标注

    Probe 阶段仅用百度渠道，不抓全文，使用 snippet 做轻量标注。
    调用者负责 commit。
    """
    try:
        task.status = "running"
        await db.flush()

        # Step 1: 搜索（仅百度）+ 存文章
        articles = await _search_and_store_articles(
            db, task, max_results=10, channels=("baidu",)
        )

        if not articles:
            task.status = "completed"
            task.articles_count = 0
            task.analysis_result = {
                "meta": {"keywords": task.keywords, "articles_total": 0, "articles_relevant": 0},
                "articles_summary": [],
            }
            await db.flush()
            return

        # Step 2: 逐篇标注（基于 snippet）
        goal = analysis_goal or task.keywords
        tags = await _tag_articles_batch(articles, analysis_goal=goal, use_full_text=False)
        await _apply_tags_to_articles(db, articles, tags)

        # Step 3: 写 analysis_result
        relevant_count = sum(
            1 for a in articles if a.relevance in ("high", "medium")
        )
        articles_summary = [
            {
                "title": a.title,
                "source_name": a.source_name,
                "source_tier": a.source_tier,
                "relevance": a.relevance,
                "sentiment": a.sentiment,
                "summary": a.summary,
            }
            for a in articles
        ]

        task.status = "completed"
        task.articles_count = len(articles)
        task.analysis_result = {
            "meta": {
                "keywords": task.keywords,
                "articles_total": len(articles),
                "articles_relevant": relevant_count,
            },
            "articles_summary": articles_summary,
        }
        await db.flush()
        logger.info("NewsTask %d: probe completed, %d articles", task.id, len(articles))

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.flush()
        logger.error("NewsTask %d: probe failed: %s", task.id, e, exc_info=True)
        raise


async def execute_news_collect(
    db: AsyncSession,
    task: NewsTask,
    analysis_goal: str = "",
    subject: str = "",
) -> None:
    """执行新闻全量采集：百度+DuckDuckGo → Crawl4AI → 逐篇标注 → 整体分析

    异步后台执行（调用方通过 asyncio.create_task 触发）。
    使用独立 db session，执行完毕后自行 commit。
    """
    try:
        task.status = "running"
        await db.flush()

        goal = analysis_goal or task.keywords
        subj = subject or task.keywords

        # Step 1: 双渠道搜索扩量 + 存文章
        articles = await _search_and_store_articles(
            db, task, max_results=50, channels=("baidu", "duckduckgo")
        )

        if not articles:
            task.status = "completed"
            task.articles_count = 0
            task.analysis_result = {"meta": {"keywords": task.keywords, "articles_total": 0}}
            await db.flush()
            return

        # Step 2: Crawl4AI 批量抓全文
        from src.news_media.article_crawler import crawl_articles

        urls = [a.url for a in articles]
        crawl_results = await crawl_articles(urls)

        articles_crawled = 0
        for article in articles:
            full_text = crawl_results.get(article.url)
            if full_text:
                await crud.update_article(db, article, {"full_text": full_text})
                articles_crawled += 1
        await db.flush()

        # Step 3: 逐篇标注（使用全文）
        # 重新加载文章以获取 full_text
        all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=100)
        tags = await _tag_articles_batch(all_articles, analysis_goal=goal, use_full_text=True)
        await _apply_tags_to_articles(db, all_articles, tags)

        # Step 4: 整体分析
        # 再次加载以获取最新标注结果
        all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=100)
        insights = await _run_insight_analysis(all_articles, analysis_goal=goal, subject=subj)

        # 补充 meta 信息
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
            task.id, len(all_articles), articles_crawled,
        )

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.commit()
        logger.error("NewsTask %d: collect failed: %s", task.id, e, exc_info=True)
