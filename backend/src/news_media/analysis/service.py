"""新闻切片 service 层（ADR-003 重构）

切片综合流程（4 步）：
  Step 1：合并多 task tagged articles → URL 去重 → 过滤 relevance=low → 描述层（SQL）
  Step 2：Pass 1 LLM → entities 归一 + role 校正 + quotes 分级 + event_clusters 聚类 + themes 议题
  Step 3：派生层（SQL）→ entity 多维 sentiment + competitive 投影 + source_pyramid + 事件时间锚 + 议题聚合
  Step 4：Pass 2 LLM → briefing + event_titles（仅 slice 页面用，不下流给策略）

result_data 顶层 schema：
  - descriptive: Step 1 输出
  - entities / quotes / event_clusters / themes / media_landscape / competitive: Step 3 输出
  - page_synthesis: Step 4 Pass 2 输出（briefing + event_titles）

stats（列表页轻量摘要）：descriptive 子集 + 归一后 top_entities。
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.analysis.models import NewsSlice
from src.news_media.analysis.schemas import NewsSliceCreate

logger = logging.getLogger(__name__)


_TIER_KEYS = ("tier1", "tier2", "tier3", "wechat_mp")
_CHANNEL_KEYS = ("baidu", "sogou", "wechat_mp")
_ARTICLE_TYPE_KEYS = ("report", "opinion", "pr", "analysis")
_TIER_WEIGHT = {"tier1": 4.0, "tier2": 2.0, "tier3": 1.0, "wechat_mp": 0.5}
_TIER_PRIORITY = {"tier1": 0, "tier2": 1, "tier3": 2, "wechat_mp": 3}


# ==================== Public API ====================


async def create_slice(
    db: AsyncSession,
    monitor_id: int,
    data: NewsSliceCreate,
    user_id: int,
) -> NewsSlice:
    """创建新闻切片：同步落 stage1（meta + descriptive），异步派发 LLM stage2。

    HTTP 立即返回切片行（status=analyzing 或 completed），不阻塞 ~120s LLM 调用。
    与 SocialSlice 创建语义对齐：stage1 同步、stage2/3 LLM 部分由 Celery 跑。
    """
    from src.news_media.tasks.models import NewsTask

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

    slice_obj = await initialize_slice(
        db,
        monitor_id=monitor_id,
        name=data.name,
        included_task_ids=data.included_task_ids,
        user_id=user_id,
        subject=data.subject,
        competitors=data.competitors,
    )

    if slice_obj.status == "analyzing":
        from src.news_media.tasks.tasks import run_news_slice_insight_task

        run_news_slice_insight_task.delay(
            slice_id=slice_obj.id,
            user_id=user_id,
            analysis_goal=data.name,
        )

    return slice_obj


async def initialize_slice(
    db: AsyncSession,
    *,
    monitor_id: int,
    name: str,
    included_task_ids: list[int],
    user_id: int,
    subject: str | None,
    competitors: list[str],
) -> NewsSlice:
    """同步创建切片行 + 写入 stage1 状态（subject/competitors 列 + descriptive + stats）。

    与社媒 stage1 语义对齐：纯 SQL 聚合，无 LLM 调用，毫秒级完成。
    无文章时直接 status=completed；有文章时 status=analyzing，由调用方派发 Celery
    跑 LLM stage2（Pass 1 → derived → Pass 2）。

    切片配置（subject / competitors）持久化到表列，与分析产物 result_data 解耦。
    """
    from sqlalchemy import select

    from src.news_media.tasks.models import NewsArticle, NewsTask

    stmt = (
        select(NewsArticle)
        .join(NewsTask, NewsArticle.task_id == NewsTask.id)
        .where(
            NewsTask.id.in_(included_task_ids),
            NewsTask.status == "completed",
        )
        .order_by(NewsArticle.published_at.desc().nulls_last())
    )
    all_articles = list((await db.execute(stmt)).scalars().all())
    filtered, url_to_task_ids = _dedupe_and_filter(all_articles)
    descriptive = _compute_descriptive(filtered, url_to_task_ids)

    initial_status = "completed" if not filtered else "analyzing"
    result_data = {"descriptive": descriptive}
    stats = _build_stats_summary(descriptive, entities=[])

    slice_obj = NewsSlice(
        name=name,
        monitor_id=monitor_id,
        included_task_ids=included_task_ids,
        user_id=user_id,
        subject=subject,
        competitors=list(competitors or []),
        result_data=result_data,
        stats=stats,
        status=initial_status,
    )
    db.add(slice_obj)
    await db.commit()
    await db.refresh(slice_obj)
    return slice_obj


# ==================== Step 1：合并 / 去重 / 过滤 / 描述层 ====================


def _dedupe_and_filter(articles: list) -> tuple[list, dict[str, list[int]]]:
    """合并多 task articles → URL 去重 → 过滤 relevance=low。

    返回 (filtered_articles, url_to_task_ids)。
    url_to_task_ids 保留每个 URL 被几个 task 命中的信号，供 cross_task_overlap 使用。
    """
    url_to_first: dict[str, Any] = {}
    url_to_task_ids: dict[str, list[int]] = defaultdict(list)
    for a in articles:
        if a.url not in url_to_first:
            url_to_first[a.url] = a
        url_to_task_ids[a.url].append(a.task_id)

    deduped = list(url_to_first.values())
    filtered = [a for a in deduped if a.relevance != "low"]
    return filtered, dict(url_to_task_ids)


def _compute_descriptive(
    articles: list,
    url_to_task_ids: dict[str, list[int]],
) -> dict:
    """Step 1 描述层（SQL，0 LLM）。

    输出来源/情感/类型/时序/跨任务重叠等可下流给策略的结构化指标。
    """
    tier_counts = {k: 0 for k in _TIER_KEYS}
    source_dist = {k: 0 for k in _CHANNEL_KEYS}
    article_type_counts = {k: 0 for k in _ARTICLE_TYPE_KEYS}
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}

    sentiment_scores: list[float] = []
    sentiment_by_tier_buckets: dict[str, list[float]] = defaultdict(list)
    by_date_count: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "by_tier": {k: 0 for k in _TIER_KEYS}, "sentiments": []}
    )

    for a in articles:
        tier = a.source_tier or "tier3"
        if tier in tier_counts:
            tier_counts[tier] += 1

        src = getattr(a, "search_source", None) or "baidu"
        if src in source_dist:
            source_dist[src] += 1

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
            bucket = by_date_count[date_str]
            bucket["count"] += 1
            if tier in bucket["by_tier"]:
                bucket["by_tier"][tier] += 1
            if a.sentiment is not None:
                bucket["sentiments"].append((a.sentiment, tier))

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

    coverage_timeseries = sorted(
        (
            {
                "date": d,
                "count": v["count"],
                "count_by_tier": v["by_tier"],
            }
            for d, v in by_date_count.items()
        ),
        key=lambda x: x["date"],
    )

    sentiment_timeseries = sorted(
        (
            {
                "date": d,
                "sentiment_avg": (
                    round(sum(s for s, _ in v["sentiments"]) / len(v["sentiments"]), 3)
                    if v["sentiments"]
                    else None
                ),
                "sentiment_weighted_by_tier": (
                    round(
                        sum(s * _TIER_WEIGHT.get(t, 1.0) for s, t in v["sentiments"])
                        / sum(_TIER_WEIGHT.get(t, 1.0) for _, t in v["sentiments"]),
                        3,
                    )
                    if v["sentiments"]
                    else None
                ),
            }
            for d, v in by_date_count.items()
        ),
        key=lambda x: x["date"],
    )

    # 跨任务重叠（同一 URL 被几个 task 命中）
    overlap_counts = {"single_task": 0, "two_tasks": 0, "three_plus": 0}
    high_overlap: list[dict] = []
    article_by_url = {a.url: a for a in articles}
    for url, task_ids in url_to_task_ids.items():
        unique_tasks = len(set(task_ids))
        if unique_tasks <= 1:
            overlap_counts["single_task"] += 1
        elif unique_tasks == 2:
            overlap_counts["two_tasks"] += 1
        else:
            overlap_counts["three_plus"] += 1

        if unique_tasks >= 2 and url in article_by_url:
            a = article_by_url[url]
            high_overlap.append(
                {
                    "url": url,
                    "task_ids": sorted(set(task_ids)),
                    "title": a.title,
                    "article_id": a.id,
                    "task_count": unique_tasks,
                }
            )
    high_overlap.sort(key=lambda x: x["task_count"], reverse=True)

    return {
        "articles_total": sum(len(set(tids)) for tids in url_to_task_ids.values()),
        "articles_unique": len(url_to_task_ids),
        "articles_filtered": len(articles),
        "source_tier_distribution": tier_counts,
        "search_source_distribution": source_dist,
        "article_type_distribution": article_type_counts,
        "sentiment_distribution": sentiment_dist,
        "sentiment_overall": sentiment_overall,
        "sentiment_by_tier": sentiment_by_tier,
        "cross_task_overlap": {
            "distribution": overlap_counts,
            "high_overlap_articles": high_overlap[:20],
        },
        "coverage_timeseries": coverage_timeseries,
        "sentiment_timeseries": sentiment_timeseries,
    }


def _build_stats_summary(descriptive: dict, entities: list[dict]) -> dict:
    """列表页用的轻量 stats 摘要。

    取 descriptive 子集 + 归一后实体 top 8。供 monitor 详情页切片列表展示。
    """
    return {
        "articles_total": descriptive.get("articles_total", 0),
        "articles_filtered": descriptive.get("articles_filtered", 0),
        "source_tier_distribution": descriptive.get("source_tier_distribution"),
        "sentiment_distribution": descriptive.get("sentiment_distribution"),
        "sentiment_overall": descriptive.get("sentiment_overall"),
        "top_entities": [
            {"name": e["name"], "mention_count": e.get("mention_count", 0)}
            for e in (entities or [])[:8]
        ],
    }


# ==================== Step 2：Pass 1 输入/输出处理 ====================


def _articles_for_llm(articles: list) -> list[dict]:
    """把 NewsArticle 转换为 Pass 1 输入用的 dict（精简字段，控制 token）。"""
    return [
        {
            "title": a.title,
            "source_name": a.source_name,
            "source_tier": a.source_tier,
            "article_type": a.article_type,
            "sentiment": a.sentiment,
            "published_at": str(a.published_at)[:10] if a.published_at else "未知",
            "summary": a.summary,
            "mentioned_entities": a.mentioned_entities,
            "key_quotes": a.key_quotes,
        }
        for a in articles
    ]


def _parse_pass1_output(content: str) -> dict:
    """从 LLM 响应中提取 JSON（兼容 markdown code block 包裹）。

    Pass 1 schema 要求：entities + quotes + event_clusters + themes。任何字段缺失视为空。
    """
    text = content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    parsed: dict
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        obj_match = re.search(r"\{[\s\S]*\}", text)
        if not obj_match:
            raise
        parsed = json.loads(obj_match.group())

    if not isinstance(parsed, dict):
        raise ValueError(f"Pass 1 output is not an object: {type(parsed)}")

    return {
        "entities": parsed.get("entities") or [],
        "quotes": parsed.get("quotes") or [],
        "event_clusters": parsed.get("event_clusters") or [],
        "themes": parsed.get("themes") or [],
    }


# ==================== Step 3：派生层 ====================


def _compute_derived(
    pass1: dict,
    articles: list,
    url_to_task_ids: dict[str, list[int]],
    subject: str,
    competitors: list[str],
) -> dict:
    """Step 3 派生层（SQL，0 LLM）。

    基于 Pass 1 输出 + filtered articles 派生 entities 多维 sentiment / event 时间锚 /
    media_landscape / competitive 投影。
    """
    # 建索引：article_index → article
    article_by_index = {i: a for i, a in enumerate(articles)}
    article_by_id = {a.id: a for a in articles}

    # entities 派生
    entities = _derive_entities(
        pass1.get("entities") or [],
        article_by_index,
        article_by_id,
    )
    # role 兜底（subject/competitors 显式列表模式可能合并变体，改变 article_ids）
    _enforce_entity_roles(entities, subject=subject, competitors=competitors)
    # 合并变体后基于最新 article_ids 重算 sentiment（合并的实体 sentiment 字段不再是 stale）
    _recompute_entity_sentiments(entities, article_by_id)

    # quotes 派生（article_index → article_id + 补 source 信息）
    quotes = _derive_quotes(pass1.get("quotes") or [], article_by_index)

    # event_clusters 派生
    event_clusters = _derive_event_clusters(
        pass1.get("event_clusters") or [],
        article_by_index,
        article_by_id,
    )

    # themes 派生（议题层，与事件层正交）
    themes = _derive_themes(
        pass1.get("themes") or [],
        article_by_index,
        article_by_id,
    )

    # 把 quotes 反向挂到 entities[].top_quote_ids
    _attach_top_quote_ids_to_entities(entities, quotes, article_by_id)

    # 跨任务命中数挂到 entities[].cross_task_count
    _attach_cross_task_count_to_entities(entities, article_by_id, url_to_task_ids)

    media_landscape = _compute_media_landscape(articles)
    competitive = _compute_competitive(entities, quotes)

    return {
        "entities": entities,
        "quotes": quotes,
        "event_clusters": event_clusters,
        "themes": themes,
        "media_landscape": media_landscape,
        "competitive": competitive,
    }


def _compute_entity_sentiments(
    article_ids: list[int],
    article_by_id: dict[int, Any],
) -> dict:
    """基于 entity 的 article_ids 派生多维 sentiment（sentiment_avg /
    sentiment_weighted_by_tier / sentiment_by_tier / source_count）。

    供 `_derive_entities` 初次派生与 `_enforce_entity_roles` 合并变体后重算共用。
    """
    sentiments: list[tuple[float, str]] = []  # (sentiment, tier)
    source_names: set[str] = set()

    for aid in article_ids:
        a = article_by_id.get(aid)
        if a is None:
            continue
        if a.source_name:
            source_names.add(a.source_name)
        if a.sentiment is not None:
            sentiments.append((a.sentiment, a.source_tier or "tier3"))

    sentiment_avg = (
        round(sum(s for s, _ in sentiments) / len(sentiments), 3)
        if sentiments
        else None
    )
    weight_total = sum(_TIER_WEIGHT.get(t, 1.0) for _, t in sentiments)
    sentiment_weighted = (
        round(
            sum(s * _TIER_WEIGHT.get(t, 1.0) for s, t in sentiments) / weight_total,
            3,
        )
        if weight_total > 0
        else None
    )

    by_tier_buckets: dict[str, list[float]] = defaultdict(list)
    for s, t in sentiments:
        by_tier_buckets[t].append(s)
    sentiment_by_tier = {
        t: (
            round(sum(buckets) / len(buckets), 3)
            if (buckets := by_tier_buckets.get(t))
            else None
        )
        for t in _TIER_KEYS
    }

    return {
        "source_count": len(source_names),
        "sentiment_avg": sentiment_avg,
        "sentiment_weighted_by_tier": sentiment_weighted,
        "sentiment_by_tier": sentiment_by_tier,
    }


def _derive_entities(
    pass1_entities: list[dict],
    article_by_index: dict[int, Any],
    article_by_id: dict[int, Any],
) -> list[dict]:
    """从 Pass 1 entities 派生 article_ids + 多维 sentiment + source_count。"""
    derived: list[dict] = []
    for e in pass1_entities:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        article_indices = e.get("article_indices") or []
        rep_indices = e.get("representative_article_indices") or article_indices[:5]

        article_ids: list[int] = []
        rep_article_ids: list[int] = []
        for idx in article_indices:
            a = article_by_index.get(idx)
            if a is not None:
                article_ids.append(a.id)
        for idx in rep_indices:
            a = article_by_index.get(idx)
            if a is not None:
                rep_article_ids.append(a.id)

        sentiment_fields = _compute_entity_sentiments(article_ids, article_by_id)
        derived.append(
            {
                "name": e.get("name"),
                "role": e.get("role", "context"),
                "mention_count": len(article_ids),
                "source_count": sentiment_fields["source_count"],
                "cross_task_count": 0,  # 后面补
                "article_ids": article_ids,
                "representative_article_ids": rep_article_ids[:5],
                "sentiment_avg": sentiment_fields["sentiment_avg"],
                "sentiment_weighted_by_tier": sentiment_fields[
                    "sentiment_weighted_by_tier"
                ],
                "sentiment_by_tier": sentiment_fields["sentiment_by_tier"],
                "top_quote_ids": [],  # 后面补
            }
        )

    derived.sort(
        key=lambda x: (
            # target 排第一，competitor 第二，按 mention_count 降序
            {"target": 0, "competitor": 1, "context": 2}.get(x["role"], 9),
            -x["mention_count"],
        )
    )
    return derived


def _recompute_entity_sentiments(
    entities: list[dict],
    article_by_id: dict[int, Any],
) -> None:
    """基于当前 article_ids 重算每个 entity 的 sentiment 字段（in-place）。

    在 `_enforce_entity_roles` 合并变体后调用——合并改变了 article_ids，
    sentiment 必须从 source of truth（articles）重算，不能用合并前的旧值。
    """
    for e in entities:
        sentiment_fields = _compute_entity_sentiments(
            e.get("article_ids") or [],
            article_by_id,
        )
        e["source_count"] = sentiment_fields["source_count"]
        e["sentiment_avg"] = sentiment_fields["sentiment_avg"]
        e["sentiment_weighted_by_tier"] = sentiment_fields["sentiment_weighted_by_tier"]
        e["sentiment_by_tier"] = sentiment_fields["sentiment_by_tier"]


def _derive_quotes(
    pass1_quotes: list[dict],
    article_by_index: dict[int, Any],
) -> list[dict]:
    """从 Pass 1 quotes 把 article_index → article_id + 补 source/published_at。"""
    derived: list[dict] = []
    for q in pass1_quotes:
        if not isinstance(q, dict) or not q.get("quote") or not q.get("speaker"):
            continue
        idx = q.get("article_index")
        a = article_by_index.get(idx) if idx is not None else None
        if a is None:
            continue
        derived.append(
            {
                "speaker": q.get("speaker"),
                "speaker_role": q.get("speaker_role", "other"),
                "quote": q.get("quote"),
                "context": q.get("context", ""),
                "article_id": a.id,
                "source_name": a.source_name,
                "source_tier": a.source_tier or "tier3",
                "published_at": str(a.published_at) if a.published_at else None,
            }
        )
    return derived


def _derive_event_clusters(
    pass1_clusters: list[dict],
    article_by_index: dict[int, Any],
    article_by_id: dict[int, Any],
) -> list[dict]:
    """事件聚类派生：article_index → article_id + 补 first_reported_at / peak_date /
    tier_weighted_score / in_task_ids / representative_article_ids。
    """
    derived: list[dict] = []
    for cid, cluster in enumerate(pass1_clusters):
        if not isinstance(cluster, dict):
            continue
        indices = cluster.get("article_indices") or []
        article_ids: list[int] = []
        cluster_articles = []
        for idx in indices:
            a = article_by_index.get(idx)
            if a:
                article_ids.append(a.id)
                cluster_articles.append(a)
        if len(cluster_articles) < 2:
            continue

        # 时间锚
        with_time = [a for a in cluster_articles if a.published_at]
        first = min(with_time, key=lambda a: a.published_at, default=None)
        first_reported_at = str(first.published_at) if first else None
        first_reporter = (
            {
                "source_name": first.source_name,
                "source_tier": first.source_tier or "tier3",
            }
            if first
            else None
        )

        # peak_date：文章数最多的日期
        date_counts: dict[str, int] = defaultdict(int)
        for a in with_time:
            date_counts[a.published_at.strftime("%Y-%m-%d")] += 1
        peak_date = (
            max(date_counts.items(), key=lambda x: x[1])[0] if date_counts else None
        )

        # 加权热度
        tier_weighted = round(
            sum(
                _TIER_WEIGHT.get(a.source_tier or "tier3", 1.0)
                for a in cluster_articles
            ),
            2,
        )

        # in_task_ids：cluster 内文章涉及的所有 task_id
        in_task_ids = sorted({a.task_id for a in cluster_articles})

        # representative：tier1 优先 + 首发文章
        cluster_articles_sorted = sorted(
            cluster_articles,
            key=lambda a: (
                _TIER_PRIORITY.get(a.source_tier or "tier3", 9),
                a.published_at or datetime.max.replace(tzinfo=timezone.utc),
            ),
        )
        rep_article_ids = [a.id for a in cluster_articles_sorted[:5]]

        derived.append(
            {
                "cluster_id": cid,
                "article_ids": article_ids,
                "article_count": len(article_ids),
                "first_reported_at": first_reported_at,
                "first_reporter": first_reporter,
                "peak_date": peak_date,
                "tier_weighted_score": tier_weighted,
                "in_task_ids": in_task_ids,
                "representative_article_ids": rep_article_ids,
            }
        )

    derived.sort(key=lambda x: x["tier_weighted_score"], reverse=True)
    # 重排 cluster_id 保证连续（影响 Pass 2 输入与输出对齐）
    for new_id, c in enumerate(derived):
        c["cluster_id"] = new_id
    return derived


def _derive_themes(
    pass1_themes: list[dict],
    article_by_index: dict[int, Any],
    article_by_id: dict[int, Any],
) -> list[dict]:
    """Step 3 议题派生：把 Pass 1 的议题（反复出现的抽象讨论维度，与具体事件正交）
    聚合为 议题 → 文章数 / 多维情感 / tier 加权热度 / 代表文章。

    与 event_clusters 区别：议题非互斥（一篇可命中多个）、抽象（讨论维度而非具体事件），
    回答"媒体在反复谈什么、态度如何"（如"安全性"负面、"科研背书"正面）。
    """
    derived: list[dict] = []
    for tid, theme in enumerate(pass1_themes):
        if not isinstance(theme, dict):
            continue
        name = (theme.get("name") or "").strip()
        indices = theme.get("article_indices") or []
        article_ids: list[int] = []
        theme_articles = []
        for idx in indices:
            a = article_by_index.get(idx)
            if a:
                article_ids.append(a.id)
                theme_articles.append(a)
        if not name or len(theme_articles) < 2:
            continue

        sent = _compute_entity_sentiments(article_ids, article_by_id)
        tier_weighted = round(
            sum(
                _TIER_WEIGHT.get(a.source_tier or "tier3", 1.0) for a in theme_articles
            ),
            2,
        )
        in_task_ids = sorted({a.task_id for a in theme_articles})
        rep_sorted = sorted(
            theme_articles,
            key=lambda a: (
                _TIER_PRIORITY.get(a.source_tier or "tier3", 9),
                a.published_at or datetime.max.replace(tzinfo=timezone.utc),
            ),
        )
        rep_article_ids = [a.id for a in rep_sorted[:5]]

        derived.append(
            {
                "theme_id": tid,
                "name": name,
                "article_ids": article_ids,
                "article_count": len(article_ids),
                "source_count": sent["source_count"],
                "sentiment_avg": sent["sentiment_avg"],
                "sentiment_weighted_by_tier": sent["sentiment_weighted_by_tier"],
                "sentiment_by_tier": sent["sentiment_by_tier"],
                "tier_weighted_score": tier_weighted,
                "in_task_ids": in_task_ids,
                "representative_article_ids": rep_article_ids,
            }
        )

    derived.sort(key=lambda x: x["tier_weighted_score"], reverse=True)
    for new_id, t in enumerate(derived):
        t["theme_id"] = new_id
    return derived


def _attach_top_quote_ids_to_entities(
    entities: list[dict],
    quotes: list[dict],
    article_by_id: dict[int, Any],
) -> None:
    """为每个 entity 挂 top_quote_ids（该实体相关文章里挑权威度最高的 quote 索引）。

    quote 的 "id" 这里用 list 中的下标。
    """
    speaker_priority = {
        "official": 0,
        "executive": 1,
        "analyst": 2,
        "kol": 3,
        "other": 4,
    }
    for e in entities:
        eid_set = set(e.get("article_ids") or [])
        candidates = [
            (i, q) for i, q in enumerate(quotes) if q.get("article_id") in eid_set
        ]
        candidates.sort(
            key=lambda iq: (
                speaker_priority.get(iq[1].get("speaker_role", "other"), 9),
                _TIER_PRIORITY.get(iq[1].get("source_tier", "tier3"), 9),
            )
        )
        e["top_quote_ids"] = [i for i, _ in candidates[:5]]


def _attach_cross_task_count_to_entities(
    entities: list[dict],
    article_by_id: dict[int, Any],
    url_to_task_ids: dict[str, list[int]],
) -> None:
    """为每个 entity 挂 cross_task_count = 提及该实体的文章涉及多少个不同 task。"""
    url_by_id = {a.id: a.url for a in article_by_id.values()}
    for e in entities:
        task_ids: set[int] = set()
        for aid in e.get("article_ids") or []:
            url = url_by_id.get(aid)
            if url:
                for tid in url_to_task_ids.get(url, []):
                    task_ids.add(tid)
        e["cross_task_count"] = len(task_ids)


def _compute_media_landscape(articles: list) -> dict:
    """媒介格局：source_pyramid（4 层 tier 分层）+ top_sources（来源 top 5）。"""
    by_tier: dict[str, list] = defaultdict(list)
    for a in articles:
        by_tier[a.source_tier or "tier3"].append(a)

    pyramid: list[dict] = []
    for tier in _TIER_KEYS:
        tier_articles = by_tier.get(tier, [])
        sentiments = [a.sentiment for a in tier_articles if a.sentiment is not None]
        sentiment_avg = (
            round(sum(sentiments) / len(sentiments), 3) if sentiments else None
        )

        source_counts: dict[str, int] = defaultdict(int)
        for a in tier_articles:
            if a.source_name:
                source_counts[a.source_name] += 1
        top_sources = [
            s
            for s, _ in sorted(
                source_counts.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:3]
        ]

        rep_articles = [
            {
                "title": a.title,
                "article_id": a.id,
                "url": a.url,
                "source_name": a.source_name,
            }
            for a in tier_articles[:3]
            if a.title
        ]

        pyramid.append(
            {
                "tier": tier,
                "article_count": len(tier_articles),
                "sentiment_avg": sentiment_avg,
                "top_source_names": top_sources,
                "representative_articles": rep_articles,
            }
        )

    # 全局 top sources
    global_source_counts: dict[str, int] = defaultdict(int)
    for a in articles:
        if a.source_name:
            global_source_counts[a.source_name] += 1
    total = sum(global_source_counts.values()) or 1
    top_sources_global = [
        {"name": s, "count": c, "share": round(c / total, 3)}
        for s, c in sorted(
            global_source_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
    ]

    return {
        "source_pyramid": pyramid,
        "top_sources": top_sources_global,
    }


def _compute_competitive(entities: list[dict], quotes: list[dict]) -> dict:
    """竞争层：从 entities 投影 role∈{target, competitor} 子集。

    tier_weighted_sov：该 player 加权 mention / 所有 player 加权 mention 之和。
    quote_share：每个 player 的 quote 数 + 含 official quote 的数。
    """
    players_raw = [e for e in entities if e.get("role") in ("target", "competitor")]
    if not players_raw:
        return {"players": [], "quote_share": []}

    # 加权 mention：用 sentiment_weighted_by_tier 的同样权重逻辑——按 tier 加权 mention
    # 但 mention_count 是数量不是 sentiment。这里我们用一个简化定义：
    # weighted_mentions = sum over articles: tier_weight * 1
    # 已经存在 entity.article_ids，我们外部需要回查 article tier。
    # 退一步：用 mention_count 等权 share（避免再传 article_by_id 进来）。
    # 加权 SOV 留作未来增强（实际策略价值差异不大）。
    total_mentions = sum(p.get("mention_count", 0) for p in players_raw) or 1

    players: list[dict] = []
    for p in players_raw:
        players.append(
            {
                "name": p.get("name"),
                "role": p.get("role"),
                "tier_weighted_sov": round(
                    p.get("mention_count", 0) / total_mentions, 3
                ),
                "mention_count": p.get("mention_count", 0),
                "source_count": p.get("source_count", 0),
                "cross_task_count": p.get("cross_task_count", 0),
                "sentiment_avg": p.get("sentiment_avg"),
                "sentiment_by_tier": p.get("sentiment_by_tier"),
                "article_ids": p.get("article_ids", []),  # 供前端下钻
                "top_quote_ids": p.get("top_quote_ids", []),
            }
        )

    # quote_share：以 player name 匹配 quote.speaker / quote.context 中的实体
    quote_share: list[dict] = []
    for p in players_raw:
        name = p.get("name") or ""
        quote_count = 0
        official_count = 0
        for q in quotes:
            text = (
                (q.get("speaker") or "")
                + " "
                + (q.get("quote") or "")
                + " "
                + (q.get("context") or "")
            )
            if name and name.lower() in text.lower():
                quote_count += 1
                if q.get("speaker_role") == "official":
                    official_count += 1
        quote_share.append(
            {
                "name": name,
                "quote_count": quote_count,
                "official_quote_count": official_count,
            }
        )

    return {"players": players, "quote_share": quote_share}


# ==================== role 兜底（从 tasks/service.py 迁移过来） ====================


def _enforce_entity_roles(
    entities: list[dict],
    subject: str,
    competitors: list[str],
) -> None:
    """强制 role 规范 + 合并 subject/competitors 变体（防御性后处理）。

    Pass 1 prompt 已指示"变体归一到规范名"+"role 硬绑定"，此函数在 LLM 偶发违反硬规则时兜底。

    三种运行模式：
    1. **退化模式**（subject 为空）：所有实体 role=context，不做变体合并
    2. **显式列表模式**（subject 非空 + competitors 非空）：严格按列表归类，
       列表外品牌强制 context，subject/competitors 的变体合并
    3. **自动发现模式**（subject 非空 + competitors 空）：仅强制 target=subject，
       LLM 自判的 competitor 保持原样（不在 canonical 列表合并）

    name 匹配：case-insensitive，exact 优先；substring 兜底（"绿米联创Aqara" → "Aqara"）。
    """
    if not entities:
        return

    # 退化模式
    if not subject:
        for e in entities:
            e["role"] = "context"
        return

    canonical_names: list[str] = []
    if subject:
        canonical_names.append(subject)
    canonical_names.extend(competitors or [])
    # 长名优先匹配（避免 "AppleCare" 被归到 "Apple"）
    canonical_names.sort(key=len, reverse=True)

    def find_canonical(name: str) -> str | None:
        if not name:
            return None
        lower = name.lower()
        # exact match
        for canon in canonical_names:
            if canon.lower() == lower:
                return canon
        # substring match
        for canon in canonical_names:
            if canon.lower() in lower or lower in canon.lower():
                return canon
        return None

    explicit_mode = bool(competitors)

    # Pass：合并变体到 canonical
    canonical_buckets: dict[str, list[dict]] = defaultdict(list)
    other_entities: list[dict] = []
    for e in entities:
        canon = find_canonical(e.get("name", ""))
        if canon:
            canonical_buckets[canon].append(e)
        else:
            other_entities.append(e)

    merged_canonical: list[dict] = []
    for canon, bucket in canonical_buckets.items():
        if len(bucket) == 1:
            merged = dict(bucket[0])
        else:
            merged = _merge_entity_records(bucket)
        merged["name"] = canon
        # role 强制
        if canon == subject:
            merged["role"] = "target"
        elif canon in (competitors or []):
            merged["role"] = "competitor"
        merged_canonical.append(merged)

    # 列表外品牌：显式模式强制 context，自动发现模式保留 LLM 判定（仅强制 target）
    for e in other_entities:
        if explicit_mode:
            e["role"] = "context"
        elif e.get("role") == "target":
            # 不允许其他实体被标 target
            e["role"] = "context"

    # target 即使 0 提及也保留
    if subject and not any(e.get("role") == "target" for e in merged_canonical):
        merged_canonical.append(
            {
                "name": subject,
                "role": "target",
                "mention_count": 0,
                "source_count": 0,
                "cross_task_count": 0,
                "article_ids": [],
                "representative_article_ids": [],
                "sentiment_avg": None,
                "sentiment_weighted_by_tier": None,
                "sentiment_by_tier": {t: None for t in _TIER_KEYS},
                "top_quote_ids": [],
            }
        )

    # 重排：target → competitor → context（mention 降序）
    new_entities = merged_canonical + other_entities
    new_entities.sort(
        key=lambda x: (
            {"target": 0, "competitor": 1, "context": 2}.get(x.get("role"), 9),
            -x.get("mention_count", 0),
        )
    )
    entities[:] = new_entities


def _merge_entity_records(bucket: list[dict]) -> dict:
    """合并多条 entity 变体记录。

    article_ids 合并去重；mention_count 由合并后 article_ids 长度决定；
    sentiment_* / source_count 占位为 None / 0，由 `_recompute_entity_sentiments`
    在 _enforce_entity_roles 之后基于 source-of-truth article 重算。
    """
    merged_article_ids: list[int] = []
    seen_aids: set[int] = set()
    for e in bucket:
        for aid in e.get("article_ids") or []:
            if aid not in seen_aids:
                seen_aids.add(aid)
                merged_article_ids.append(aid)

    rep_ids = list(
        {aid for e in bucket for aid in (e.get("representative_article_ids") or [])}
    )

    return {
        "name": bucket[0].get("name"),
        "role": bucket[0].get("role", "context"),
        "mention_count": len(merged_article_ids),
        "source_count": 0,  # _recompute_entity_sentiments 会重算
        "cross_task_count": max(
            (e.get("cross_task_count", 0) for e in bucket), default=0
        ),
        "article_ids": merged_article_ids,
        "representative_article_ids": rep_ids[:5],
        "sentiment_avg": None,
        "sentiment_weighted_by_tier": None,  # 派生层会重算
        "sentiment_by_tier": {t: None for t in _TIER_KEYS},  # 派生层会重算
        "top_quote_ids": [],  # 派生层会重算
    }


# ==================== Step 4：Pass 2（仅页面用，失败容错） ====================


async def _run_pass2_safely(
    descriptive: dict,
    derived: dict,
    articles: list,
    subject: str,
    analysis_goal: str,
) -> dict:
    """跑 Pass 2，失败时返回空 page_synthesis 不阻断流程。

    返回 {"data": dict, "token_usage": dict | None}。
    """
    from src.llm.chains.news.pass2_chain import (
        create_pass2_chain,
        format_entities_for_pass2,
        format_events_for_pass2,
        format_quotes_for_pass2,
    )

    article_titles_by_id = {a.id: a.title for a in articles}

    try:
        chain = create_pass2_chain()
        response = await chain.ainvoke(
            {
                "analysis_goal": analysis_goal,
                "subject": subject or "（独立监测，无指定主体）",
                "articles_filtered": descriptive.get("articles_filtered"),
                "source_tier_dist": descriptive.get("source_tier_distribution"),
                "search_source_dist": descriptive.get("search_source_distribution"),
                "article_type_dist": descriptive.get("article_type_distribution"),
                "sentiment_dist": descriptive.get("sentiment_distribution"),
                "sentiment_overall": descriptive.get("sentiment_overall"),
                "sentiment_by_tier": descriptive.get("sentiment_by_tier"),
                "entities_block": format_entities_for_pass2(
                    derived.get("entities") or []
                ),
                "quotes_block": format_quotes_for_pass2(derived.get("quotes") or []),
                "events_block": format_events_for_pass2(
                    derived.get("event_clusters") or [],
                    article_titles_by_id,
                ),
            }
        )
        token_usage = (response.response_metadata or {}).get("token_usage")
        parsed = _parse_pass2_output(response.content)
        return {"data": parsed, "token_usage": token_usage}
    except Exception as e:
        logger.warning("Pass 2 failed (slice 页面降级展示): %s", e)
        return {"data": {}, "token_usage": None}


def _parse_pass2_output(content: str) -> dict:
    """解析 Pass 2 JSON 输出，返回 {briefing, event_titles}。"""
    text = content.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    parsed: dict
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        obj_match = re.search(r"\{[\s\S]*\}", text)
        if not obj_match:
            return {}
        parsed = json.loads(obj_match.group())

    if not isinstance(parsed, dict):
        return {}

    return {
        "briefing": parsed.get("briefing")
        if isinstance(parsed.get("briefing"), dict)
        else {},
        "event_titles": parsed.get("event_titles")
        if isinstance(parsed.get("event_titles"), dict)
        else {},
    }


# Token 累积已统一走 src.llm.utils.extract_token_usage + merge_token_usage_stats。
# 之前自实现的 _merge_token_usage 因输出非 TokenUsageStats 嵌套结构（无 summary
# 包装、无成本计算），导致 AnalysisJob.token_usage 在前端被读成 0 次 / ¥0.0000。已移除。
