"""新闻任务服务层

- 独立 news monitor 场景：一步式采集任务（phase=collect 或 None），走 celery
- strategy 研究场景：策略侧自己管理 probe/collect 两段式调度，本模块只
  提供底层 execute_news_probe / celery 任务，approve/refine 入口不对外暴露
  （策略通过 strategies/service.py 的批量端点处理）

collect 阶段的执行流水线位于 src/news_media/tasks/tasks.py，
本模块内的辅助函数（_tag_articles_batch / _run_insight_analysis）供 celery
_async_run_collect 直接引用。
"""

import json
import logging
import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.config import settings
from src.news_media.tasks import crud
from src.news_media.tasks.models import NewsArticle, NewsTask
from src.news_media.tasks.schemas import NewsTaskCreate

logger = logging.getLogger(__name__)

# probe 搜索每渠道最大条数(业务策略,不进 config)
_PROBE_MAX_RESULTS = 20
_DEFAULT_CHANNELS: tuple[str, ...] = ("baidu", "sogou", "duckduckgo")
_ALL_VALID_CHANNELS = {"baidu", "sogou", "duckduckgo", "wechat_mp"}


def _resolve_channels(task: "NewsTask") -> tuple[str, ...]:
    """从 task.search_params 读取用户选择的搜索渠道，fallback 到默认三渠道。"""
    params = task.search_params or {}
    raw = params.get("channels")
    if not raw or not isinstance(raw, list):
        return _DEFAULT_CHANNELS
    valid = tuple(ch for ch in raw if ch in _ALL_VALID_CHANNELS)
    return valid or _DEFAULT_CHANNELS


async def create_news_task(
    db: AsyncSession,
    monitor_id: int,
    data: NewsTaskCreate,
    user_id: int,
    strategy_id: int | None = None,
    phase: str | None = None,
) -> NewsTask:
    """创建新闻任务。

    Note: 内部 `await db.commit()` 是有意设计。编排函数中途异常时，已 commit
    的孤立任务由 Monitor CASCADE 级联删除兜底。详见 backend/CLAUDE.md §事务策略。
    """
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
        "user_id": user_id,
    }
    task = await crud.create_task(db, task_data)
    await db.commit()
    await db.refresh(task, ["monitor", "user"])
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


# ==================== Internal Helpers (shared with celery collect) ====================


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


async def _run_insight_analysis(
    articles: list,
    analysis_goal: str,
    subject: str,
) -> tuple[dict, dict | None]:
    """整体分析（一次 LLM 调用），返回 (结构化洞察, token_usage)。

    token_usage 来自 LLM response_metadata，可能为 None。
    """
    from src.llm.chains.news.insight_chain import (
        create_insight_chain as create_news_insight_chain,
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

    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0, "wechat_mp": 0}
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
        "wechat_mp_count": tier_counts["wechat_mp"],
    })

    token_usage = (response.response_metadata or {}).get("token_usage")

    try:
        return _parse_llm_json(response.content), token_usage
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse insight response: %s", e)
        return {"error": str(e)}, token_usage


# ==================== Sync helpers for Celery gevent worker ====================
# Celery 任务（gevent pool）直接调用这些同步函数，走 SyncSessionLocal + psycopg。
# 避免在 gevent worker 里引入 asyncio event loop（asyncpg 连接绑定 loop 会造成
# 跨 loop 并发 dispose 竞态，导致 greenlet 永久卡死）。
# FastAPI 路由的 async 调用路径使用上面的 _run_insight_analysis（async 版本）。


def _search_and_store_articles_sync(
    db: Session,
    task: NewsTask,
    max_results: int = 10,
    channels: tuple = ("baidu",),
) -> list[NewsArticle]:
    """搜索 + 创建 NewsArticle（同步版）"""
    from src.news_media.tasks.news_search.aggregator import search_news

    search_results = search_news(
        query=task.keywords,
        max_results=max_results,
        channels=list(channels),
    )
    if not search_results:
        return []

    articles: list[NewsArticle] = []
    for r in search_results:
        article = NewsArticle(
            task_id=task.id,
            url=r["url"],
            title=r["title"],
            snippet=r.get("snippet"),
            source_name=r["source_name"],
            source_tier=r["source_tier"],
            search_source=r.get("search_source", "baidu"),
            published_at=r.get("published_at"),
            image_url=r.get("image_url"),
            raw_data=r.get("raw_data"),
        )
        db.add(article)
        articles.append(article)
    db.flush()
    return articles


def _tag_articles_batch_sync(
    articles: list,
    analysis_goal: str,
    use_full_text: bool = False,
) -> tuple[list[dict], dict | None]:
    """逐篇轻量标注（同步版，chain.invoke）"""
    from src.llm.chains.news.tagging_chain import (
        create_tagging_chain,
        format_articles_for_tagging,
    )

    chain = create_tagging_chain()
    all_tags: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0

    batch_size = settings.CELERY_AI_NEWS_TAGGING_BATCH_SIZE
    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
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
        response = chain.invoke({
            "analysis_goal": analysis_goal,
            "article_count": len(batch),
            "articles_content": articles_content,
        })

        usage = (response.response_metadata or {}).get("token_usage") or {}
        total_input_tokens += usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
        total_output_tokens += usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

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

    token_usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
    } if (total_input_tokens or total_output_tokens) else None

    return all_tags, token_usage


def _apply_tags_to_articles_sync(
    db: Session,
    articles: list,
    tags: list[dict],
) -> None:
    """将标注结果写回 NewsArticle（同步版）"""
    for tag in tags:
        idx = tag.get("article_index")
        if idx is None or idx >= len(articles):
            continue
        article = articles[idx]
        if "relevance" in tag:
            article.relevance = tag["relevance"]
        if "sentiment" in tag:
            article.sentiment = tag["sentiment"]
        if "article_type" in tag:
            article.article_type = tag["article_type"]
        if "mentioned_entities" in tag:
            article.mentioned_entities = tag["mentioned_entities"]
        if "key_quotes" in tag:
            article.key_quotes = tag["key_quotes"]
        if "summary" in tag:
            article.summary = tag["summary"]
    db.flush()


def _run_insight_analysis_sync(
    articles: list,
    analysis_goal: str,
    subject: str,
) -> tuple[dict, dict | None]:
    """整体分析（同步版，chain.invoke）"""
    from src.llm.chains.news.insight_chain import (
        create_insight_chain as create_news_insight_chain,
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

    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0, "wechat_mp": 0}
    for a in relevant:
        tier = a.source_tier or "tier3"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    tagged_content = format_tagged_articles_for_insight(article_dicts)

    chain = create_news_insight_chain()
    response = chain.invoke({
        "analysis_goal": analysis_goal,
        "subject": subject,
        "article_count": len(relevant),
        "tagged_articles": tagged_content,
        "tier1_count": tier_counts["tier1"],
        "tier2_count": tier_counts["tier2"],
        "tier3_count": tier_counts["tier3"],
        "wechat_mp_count": tier_counts["wechat_mp"],
    })

    token_usage = (response.response_metadata or {}).get("token_usage")

    try:
        return _parse_llm_json(response.content), token_usage
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse insight response: %s", e)
        return {"error": str(e)}, token_usage


def execute_news_probe_sync(
    db: Session,
    task: NewsTask,
) -> None:
    """执行新闻探测（同步版）：仅搜索 + 落库，不抓全文、不打标。

    调用者负责 commit。本函数运行在 Celery gevent worker 里。
    """
    try:
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        db.flush()

        articles = _search_and_store_articles_sync(
            db, task, max_results=_PROBE_MAX_RESULTS, channels=_resolve_channels(task)
        )

        tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0, "wechat_mp": 0}
        source_samples: list[str] = []
        seen_sources: set[str] = set()
        for a in articles:
            tier = a.source_tier or "tier3"
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            if a.source_name and a.source_name not in seen_sources:
                seen_sources.add(a.source_name)
                if len(source_samples) < 8:
                    source_samples.append(a.source_name)

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.articles_count = len(articles)
        task.analysis_result = {
            "meta": {
                "keywords": task.keywords,
                "articles_total": len(articles),
                "source_tier_distribution": tier_counts,
                "source_samples": source_samples,
            },
        }
        db.flush()
        logger.info(
            "NewsTask %d: probe completed, %d articles",
            task.id, task.articles_count,
        )

    except Exception as e:
        task.status = "failed"
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = str(e)
        db.flush()
        logger.error("NewsTask %d: probe failed: %s", task.id, e, exc_info=True)
        raise

