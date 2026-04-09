"""新闻任务服务层（含执行逻辑与 LLM 辅助函数）"""

import json
import logging
import re

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.tasks import crud
from src.news_media.tasks.models import NewsTask
from src.news_media.tasks.schemas import NewsTaskCreate

logger = logging.getLogger(__name__)

# 逐篇标注的批次大小
_TAGGING_BATCH_SIZE = 5


async def create_news_task(
    db: AsyncSession,
    monitor_id: int,
    data: NewsTaskCreate,
    user_id: int,
    strategy_id: int | None = None,
    phase: str | None = None,
) -> NewsTask:
    """创建新闻任务"""
    from src.news_media.monitors.crud import get_monitor_by_id

    monitor = await get_monitor_by_id(db, monitor_id, load_relations=False)
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
        "auto_analyze": data.auto_analyze,
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
    """从 LLM 响应中提取 JSON（兼容 markdown code block 包裹）"""
    text = content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        return json.loads(array_match.group())

    return json.loads(content)


async def _search_and_store_articles(
    db: AsyncSession,
    task: NewsTask,
    max_results: int = 10,
    channels: tuple = ("baidu",),
) -> list:
    """双渠道搜索 + 创建 NewsArticle（绑定 task_id），返回本次创建的文章列表"""
    from src.news_media.tasks.news_search.aggregator import search_news

    search_results = await search_news(
        query=task.keywords,
        max_results=max_results,
        channels=list(channels),
    )
    if not search_results:
        return []

    articles_data = [
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
    ]

    articles = await crud.bulk_create_articles(db, articles_data)
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
                for tag in tags:
                    if isinstance(tag, dict) and "article_index" in tag:
                        tag["article_index"] = i + tag["article_index"]
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

        goal = analysis_goal or task.keywords
        tags = await _tag_articles_batch(articles, analysis_goal=goal, use_full_text=False)
        await _apply_tags_to_articles(db, articles, tags)

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
                "articles_total": task.articles_count,
                "articles_relevant": relevant_count,
            },
            "articles_summary": articles_summary,
        }
        await db.flush()
        logger.info("NewsTask %d: probe completed, %d articles", task.id, task.articles_count)

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

        articles = await _search_and_store_articles(
            db, task, max_results=50, channels=("baidu", "duckduckgo")
        )

        if not articles:
            task.status = "completed"
            task.articles_count = 0
            task.analysis_result = {"meta": {"keywords": task.keywords, "articles_total": 0}}
            await db.flush()
            return

        from src.news_media.tasks.article_crawler import crawl_articles

        urls = [a.url for a in articles]
        crawl_results = await crawl_articles(urls)

        articles_crawled = 0
        for article in articles:
            full_text = crawl_results.get(article.url)
            if full_text:
                await crud.update_article(db, article, {"full_text": full_text})
                articles_crawled += 1
        await db.flush()

        all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=100)
        tags = await _tag_articles_batch(all_articles, analysis_goal=goal, use_full_text=True)
        await _apply_tags_to_articles(db, all_articles, tags)

        all_articles, _ = await crud.get_articles_by_task(db, task.id, limit=100)
        insights = await _run_insight_analysis(all_articles, analysis_goal=goal, subject=subj)

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
        task.articles_count = len(articles)
        task.analysis_result = analysis_result
        await db.commit()
        logger.info(
            "NewsTask %d: collect completed, %d articles, %d crawled",
            task.id, task.articles_count, articles_crawled,
        )

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.commit()
        logger.error("NewsTask %d: collect failed: %s", task.id, e, exc_info=True)
