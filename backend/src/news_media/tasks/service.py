"""新闻任务服务层

- 独立 news monitor 场景：一步式采集任务（phase=collect 或 None），走 celery
- strategy 研究场景：策略侧自己管理 probe/collect 两段式调度，本模块只
  提供底层 execute_news_probe / celery 任务，approve/refine 入口不对外暴露
  （策略通过 strategies/service.py 的批量端点处理）

collect 阶段的执行流水线位于 src/news_media/tasks/tasks.py，本模块内的辅助函数
（_tag_articles_batch_sync / _apply_tags_to_articles_sync / _compute_task_stats）
供 celery 直接调用。Slice 综合分析（Pass 1 + Pass 2）由 src/news_media/analysis/
service.py 承担，task 层不再调 insight。
"""

import json
import logging
import re
import time
from collections import defaultdict
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
_DEFAULT_CHANNELS: tuple[str, ...] = ("baidu", "sogou")
_ALL_VALID_CHANNELS = {"baidu", "sogou", "wechat_mp"}


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
        db,
        skip=skip,
        limit=page_size,
        monitor_id=monitor_id,
        status=status_filter,
        phase=phase,
        search=search,
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


# ==================== Sync helpers for Celery gevent worker ====================
# Celery 任务（gevent pool）直接调用这些同步函数，走 SyncSessionLocal + psycopg。
# 避免在 gevent worker 里引入 asyncio event loop（asyncpg 连接绑定 loop 会造成
# 跨 loop 并发 dispose 竞态，导致 greenlet 永久卡死）。


def _search_and_store_articles_sync(
    db: Session,
    task: NewsTask,
    max_results: int = 10,
    channels: tuple = ("baidu",),
    raw_counts_out: dict[str, int] | None = None,
) -> list[NewsArticle]:
    """搜索 + 创建 NewsArticle（同步版）

    Args:
        raw_counts_out: 可选输出字典。若提供，aggregator 会填入去重前的
            每渠道原始召回量（调用方可用于持久化到 task.analysis_result）。
    """
    from src.news_media.tasks.news_search.aggregator import search_news

    search_results = search_news(
        query=task.keywords,
        max_results=max_results,
        channels=list(channels),
        raw_counts_out=raw_counts_out,
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
    subject: str = "",
    competitors: list[str] | None = None,
) -> tuple[list[dict], dict | None]:
    """逐篇轻量标注（同步版，chain.invoke）

    subject / competitors：研究主体与已知竞品列表，供 role 硬绑定使用。
    策略场景由 slice_blueprint[].subject/competitors 传入；独立监测场景传空，
    chain 退化为全部 context。

    返回 (tags, token_usage)；token_usage 为 ``{summary, call_details}`` 嵌套结构
    （由 :func:`extract_token_usage` + :func:`merge_token_usage_stats` 累积每个 batch
    的 LLM 调用），调用方直接传给 ``complete_analysis_job_sync(token_usage=...)`` 即可。
    前端读 ``summary.total_calls`` / ``summary.total_cost_cny`` 渲染 AI 统计。
    """
    from src.llm.chains.news.tagging_chain import (
        create_tagging_chain,
        format_articles_for_tagging,
    )
    from src.llm.utils import extract_token_usage, merge_token_usage_stats

    chain = create_tagging_chain()
    all_tags: list[dict] = []
    token_usage: dict | None = None

    competitors_str = ", ".join(competitors or []) or "（未指定）"
    subject_str = subject or ""

    batch_size = settings.CELERY_AI_NEWS_TAGGING_BATCH_SIZE
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        batch_dicts = [
            {
                "title": a.title,
                "source_name": a.source_name,
                "snippet": a.snippet,
                "full_text": a.full_text if use_full_text else None,
            }
            for a in batch
        ]

        articles_content = format_articles_for_tagging(
            batch_dicts, use_full_text=use_full_text
        )
        batch_start = time.time()
        response = chain.invoke(
            {
                "analysis_goal": analysis_goal,
                "subject": subject_str,
                "competitors": competitors_str,
                "article_count": len(batch),
                "articles_content": articles_content,
            }
        )
        batch_usage = extract_token_usage(
            response,
            duration_seconds=time.time() - batch_start,
        )
        token_usage = merge_token_usage_stats(token_usage, batch_usage)

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


_TIER_KEYS = ("tier1", "tier2", "tier3", "wechat_mp")
_CHANNEL_KEYS = ("baidu", "sogou", "wechat_mp")
_ARTICLE_TYPE_KEYS = ("report", "opinion", "pr", "analysis")
_RELEVANCE_KEYS = ("high", "medium", "low")
# tier1 优先；同 tier 内保持原顺序（list 拼接 + 稳定排序保证）
_TIER_PRIORITY = {"tier1": 0, "tier2": 1, "tier3": 2, "wechat_mp": 3}


def _compute_task_stats(articles: list) -> dict:
    """从已标注 NewsArticle 列表派生 task 描述统计。

    供 collect celery 任务调用，写入 task.analysis_result.meta；不调 LLM。
    所有指标基于 tagging 阶段产出聚合，是事实层。
    """
    tier_counts = {k: 0 for k in _TIER_KEYS}
    source_dist = {k: 0 for k in _CHANNEL_KEYS}
    article_type_counts = {k: 0 for k in _ARTICLE_TYPE_KEYS}
    relevance_counts = {k: 0 for k in _RELEVANCE_KEYS}
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}

    sentiment_scores: list[float] = []
    sentiment_by_tier_buckets: dict[str, list[float]] = defaultdict(list)
    entity_mentions: dict[str, int] = {}
    by_date: dict[str, dict] = defaultdict(
        lambda: {
            "count": 0,
            "by_tier": {k: 0 for k in _TIER_KEYS},
            "sentiments": [],
        }
    )
    quotes_with_priority: list[tuple[int, dict]] = []

    for a in articles:
        tier = a.source_tier or "tier3"
        if tier in tier_counts:
            tier_counts[tier] += 1

        src = getattr(a, "search_source", None) or "baidu"
        if src in source_dist:
            source_dist[src] += 1

        if a.relevance in relevance_counts:
            relevance_counts[a.relevance] += 1

        if a.article_type in article_type_counts:
            article_type_counts[a.article_type] += 1

        if a.sentiment is not None:
            sentiment_scores.append(a.sentiment)
            sentiment_by_tier_buckets[tier].append(a.sentiment)
            if a.sentiment > 0:
                sentiment_dist["positive"] += 1
            elif a.sentiment < 0:
                sentiment_dist["negative"] += 1
            else:
                sentiment_dist["neutral"] += 1

        if a.published_at:
            date_str = a.published_at.strftime("%Y-%m-%d")
            bucket = by_date[date_str]
            bucket["count"] += 1
            if tier in bucket["by_tier"]:
                bucket["by_tier"][tier] += 1
            if a.sentiment is not None:
                bucket["sentiments"].append(a.sentiment)

        # 实体原始计数（不归一，归一是 slice 的事）
        for ent in a.mentioned_entities or []:
            name = (ent or {}).get("name", "")
            if name:
                entity_mentions[name] = entity_mentions.get(name, 0) + 1

        for q in a.key_quotes or []:
            speaker = (q or {}).get("speaker", "")
            quote_text = (q or {}).get("quote", "")
            if speaker and quote_text:
                quotes_with_priority.append(
                    (
                        _TIER_PRIORITY.get(tier, 99),
                        {
                            "speaker": speaker,
                            "quote": quote_text,
                            "source_name": a.source_name,
                            "source_tier": tier,
                            "article_id": a.id,
                        },
                    )
                )

    sentiment_overall = (
        round(sum(sentiment_scores) / len(sentiment_scores), 3)
        if sentiment_scores
        else None
    )

    sentiment_by_tier = {
        t: (
            round(sum(scores) / len(scores), 3)
            if (scores := sentiment_by_tier_buckets.get(t))
            else None
        )
        for t in _TIER_KEYS
    }

    coverage_by_day = sorted(
        (
            {
                "date": d,
                "count": v["count"],
                "count_by_tier": v["by_tier"],
                "sentiment_avg": (
                    round(sum(v["sentiments"]) / len(v["sentiments"]), 3)
                    if v["sentiments"]
                    else None
                ),
            }
            for d, v in by_date.items()
        ),
        key=lambda x: x["date"],
    )

    top_entities_raw = sorted(
        ({"name": k, "mention_count": v} for k, v in entity_mentions.items()),
        key=lambda x: x["mention_count"],
        reverse=True,
    )[:10]

    quotes_with_priority.sort(key=lambda x: x[0])
    top_quotes = [q for _, q in quotes_with_priority[:5]]

    return {
        "articles_total": len(articles),
        "articles_high": relevance_counts["high"],
        "articles_medium": relevance_counts["medium"],
        "articles_low": relevance_counts["low"],
        "source_tier_distribution": tier_counts,
        "search_source_distribution": source_dist,
        "article_type_distribution": article_type_counts,
        "sentiment_distribution": sentiment_dist,
        "sentiment_overall": sentiment_overall,
        "sentiment_by_tier": sentiment_by_tier,
        "coverage_by_day": coverage_by_day,
        "top_entities_raw": top_entities_raw,
        "top_quotes": top_quotes,
    }


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

        raw_counts: dict[str, int] = {}
        articles = _search_and_store_articles_sync(
            db,
            task,
            max_results=_PROBE_MAX_RESULTS,
            channels=_resolve_channels(task),
            raw_counts_out=raw_counts,
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
                "channel_raw_counts": raw_counts,
            },
        }
        db.flush()
        logger.info(
            "NewsTask %d: probe completed, %d articles",
            task.id,
            task.articles_count,
        )

    except Exception as e:
        task.status = "failed"
        task.completed_at = datetime.now(timezone.utc)
        task.error_message = str(e)
        db.flush()
        logger.error("NewsTask %d: probe failed: %s", task.id, e, exc_info=True)
        raise
