"""probe 阶段专用轻量聚合。

目的：给 probe review chain 提供判断关键词质量所需的 4 个粗粒度信号，
不调 LLM，不计算切片 / 洞察 / IPA / context graph 等完整阶段才需要的指标。

与完整 `aggregate_task_analysis` 的关系：
- 产出 shape 是完整结果的严格子集（字段路径一致：meta.data_volume / metrics.marketing_analysis
  / insights.{target_entities, competitor_entities, top_topics}），`_build_probe_task_summaries`
  读取时无需任何特殊分支
- 不包含 `aggregated_opinions` / `aggregated_entities` 等切片消费字段——这些只有在
  collect 阶段跑完完整 aggregation 才会有，phase 推进后由完整路径覆写 task.analysis_result
- 耗时 <1s（纯 SQL + Python 计数），替代完整路径的 60-90s wall time

正确性边界：
- 实体/话题不做跨 post 语义归一（"索尼 WH-1000XM6" vs "Sony WH1000XM6" 视为两个实体）。
  对 `entity_match` bool 判断无影响；对 top_topics 频次排序略有稀释但仍反映趋势
- target / competitor 分类用 task_keywords 子串匹配（关键词在实体名里 or 实体名在关键词里）。
  对标准用法（关键词 = 品牌/产品名）足够准；极端情况下 raw 关键词与 entity 文本差距过大可能漏判
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.social_media.analysis.constants import SPAM_HIGH_THRESHOLD
from src.social_media.analysis.models import PostAnalysis
from src.social_media.tasks.models import SocialPost, SocialTask


def build_probe_aggregation(
    db: Session,
    task_id: int,
    spam_threshold: float = SPAM_HIGH_THRESHOLD,
) -> dict[str, Any]:
    """为 probe 任务生成轻量聚合结果。

    Args:
        db: 同步数据库会话
        task_id: SocialTask ID
        spam_threshold: spam 分组阈值（>= 视为推广）

    Returns:
        dict：与完整 aggregation 字段路径兼容的子集，可直接写入 `task.analysis_result`。
        `_build_probe_task_summaries` 消费的所有字段都在其中。
    """
    # 0. 任务关键词（用于 target/competitor 分类）
    task = db.execute(select(SocialTask).where(SocialTask.id == task_id)).scalar_one_or_none()
    task_keywords: list[str] = []
    if task and task.keywords:
        task_keywords = [k.strip() for k in task.keywords.split(",") if k.strip()]

    # 1. 所有 PostAnalysis 行 + 原文总数
    analyses = list(
        db.execute(
            select(PostAnalysis).where(PostAnalysis.task_id == task_id)
        ).scalars().all()
    )
    total_posts = int(
        db.execute(
            select(func.count(SocialPost.id)).where(
                SocialPost.task_id == task_id,
                SocialPost.is_deleted.is_(False),
            )
        ).scalar()
        or 0
    )

    screened = sum(1 for a in analyses if a.spam_score is not None)
    deep_analyzed = sum(1 for a in analyses if a.post_deep_result)

    # 2. 实体分类 + 话题频次（单次遍历）
    seen_targets: set[str] = set()
    seen_competitors: set[str] = set()
    target_entities: list[dict[str, Any]] = []
    competitor_entities: list[dict[str, Any]] = []
    topic_mentions: Counter[str] = Counter()
    topic_post_sources: dict[str, set[int]] = defaultdict(set)

    for analysis in analyses:
        pdr = analysis.post_deep_result or {}
        if not pdr:
            continue

        # 实体
        for ent in pdr.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            name = (ent.get("name") or "").strip()
            etype = (ent.get("type") or "").strip()
            if not name:
                continue
            if _matches_keywords(name, task_keywords):
                if name not in seen_targets:
                    seen_targets.add(name)
                    target_entities.append({"name": name, "type": etype})
            elif etype in ("品牌", "产品"):
                if name not in seen_competitors:
                    seen_competitors.add(name)
                    competitor_entities.append({"name": name, "type": etype})

        # 话题（用原始 category 作 name，不做 LLM 归一）
        for op in pdr.get("general_opinions") or []:
            if not isinstance(op, dict):
                continue
            category = (op.get("category") or "").strip()
            if not category:
                continue
            topic_mentions[category] += 1
            topic_post_sources[category].add(analysis.post_id)

    top_topics = [
        {
            "name": name,
            "mentions": mentions,
            "post_source_count": len(topic_post_sources[name]),
        }
        for name, mentions in topic_mentions.most_common(20)
    ]

    # 3. 营销占比（用 screened 分母；无 screening 时 0）
    scored = [a.spam_score for a in analyses if a.spam_score is not None]
    if scored:
        promotion_ratio = sum(1 for s in scored if s >= spam_threshold) / len(scored)
    else:
        promotion_ratio = 0.0

    return {
        "meta": {
            "task_id": task_id,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "keywords": task_keywords,
            "data_volume": {
                "total": total_posts,
                "screened": screened,
                "deep_analyzed": deep_analyzed,
                "comment_analyzed": 0,  # probe 阶段不抓评论
            },
            "probe_lite": True,  # 标记：区别于完整 aggregation 结果
        },
        "metrics": {
            "marketing_analysis": {
                "promotion_ratio": round(promotion_ratio, 3),
            },
        },
        "insights": {
            "target_entities": target_entities,
            "competitor_entities": competitor_entities,
            "top_topics": top_topics,
        },
    }


def _matches_keywords(entity_name: str, task_keywords: list[str]) -> bool:
    """实体名与任务关键词的子串双向匹配。

    `"索尼 WH-1000XM6" 包含关键词 "索尼"` → True
    `关键词 "索尼WH-1000XM6" 包含实体名 "WH-1000XM6"` → True
    空关键词列表直接返回 False，避免所有实体都被误判为 target。
    """
    if not task_keywords:
        return False
    name_lower = entity_name.lower()
    for kw in task_keywords:
        kw_lower = kw.lower()
        if not kw_lower:
            continue
        if kw_lower in name_lower or name_lower in kw_lower:
            return True
    return False
