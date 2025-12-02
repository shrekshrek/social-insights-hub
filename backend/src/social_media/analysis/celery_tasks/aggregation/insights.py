"""派生洞察模块

从 aggregated_entities 和 aggregated_opinions 派生的高级洞察：
- 场景与人群画像 (derive_context_analysis)
- KANO 需求分层 (classify_kano_model)
- 竞品分析 (analyze_competition)
- KOL 声音提取 (extract_kol_voices)

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md
"""

import logging
from typing import Any
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.social_media.tasks.models import SocialPost

logger = logging.getLogger(__name__)


# ============================================================================
# 场景与人群画像聚合 (§4.5.4) - 从 aggregated_entities 派生
# ============================================================================

def derive_context_analysis(
    aggregated_entities: list[dict[str, Any]],
    min_mentions: int = 2,
    top_n: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """从 aggregated_entities 派生场景与人群画像

    采用"先融合，后派生"架构：
    - 输入: aggregate_entities() 返回的 aggregated_entities（已完成实体名称归一化，数组格式）
    - 输出: 场景和人群画像的聚合结果

    优势：
    1. 数据一致性：复用实体归一化结果，避免重复处理
    2. 维度完整性：scenarios/audience 已关联到归一化实体
    3. 追溯能力：通过 post_ids 支持反向追溯

    Args:
        aggregated_entities: aggregate_entities 返回的 aggregated_entities 字段（数组格式）
        min_mentions: 最小提及数门槛（过滤偶然数据）
        top_n: 返回前 N 个

    Returns:
        dict: {
            "scenarios": [{"label": "游戏", "heat": 3000, "associated_issues": [...], ...}],
            "audiences": [{"label": "学生党", "heat": 2000, "preferences": [...]}],
        }
    """
    # 收集场景数据
    scenario_data: dict[str, dict] = defaultdict(lambda: {
        "label": "",
        "total_heat": 0.0,
        "post_ids": set(),
        "associated_issues": defaultdict(int),
        "associated_features": defaultdict(int),
    })

    # 收集人群数据
    audience_data: dict[str, dict] = defaultdict(lambda: {
        "label": "",
        "total_heat": 0.0,
        "post_ids": set(),
        "preferences": defaultdict(int),  # 关联的 market_factors 或 features
    })

    # 遍历所有已归一化的实体（数组格式）
    for entity in aggregated_entities:
        entity_heat = entity.get("heat", 0)
        entity_issues = entity.get("issues", [])  # [{"text": ..., "post_ids": [...]}]
        entity_features = entity.get("features", [])
        entity_market_factors = entity.get("market_factors", [])
        entity_scenarios = entity.get("scenarios", [])
        entity_audiences = entity.get("audience", [])

        # 处理场景
        for scenario_item in entity_scenarios:
            scenario_text = scenario_item.get("text", "")
            scenario_post_ids = scenario_item.get("post_ids", [])

            if not scenario_text:
                continue

            data = scenario_data[scenario_text]
            data["label"] = scenario_text
            # 使用实体的 heat 作为场景热度贡献
            data["total_heat"] += entity_heat
            # 累加帖子ID
            data["post_ids"].update(scenario_post_ids)

            # 关联 issues 和 features（来自同一实体）
            for issue_item in entity_issues:
                issue_text = issue_item.get("text", "")
                if issue_text:
                    data["associated_issues"][issue_text] += len(issue_item.get("post_ids", []))
            for feature_item in entity_features:
                feature_text = feature_item.get("text", "")
                if feature_text:
                    data["associated_features"][feature_text] += len(feature_item.get("post_ids", []))

        # 处理人群画像
        for audience_item in entity_audiences:
            audience_text = audience_item.get("text", "")
            audience_post_ids = audience_item.get("post_ids", [])

            if not audience_text:
                continue

            data = audience_data[audience_text]
            data["label"] = audience_text
            data["total_heat"] += entity_heat
            data["post_ids"].update(audience_post_ids)

            # 关联偏好（market_factors + features）
            for factor_item in entity_market_factors:
                factor_text = factor_item.get("text", "")
                if factor_text:
                    data["preferences"][factor_text] += len(factor_item.get("post_ids", []))
            for feature_item in entity_features:
                feature_text = feature_item.get("text", "")
                if feature_text:
                    data["preferences"][feature_text] += len(feature_item.get("post_ids", []))

    # 格式化场景输出（置信度过滤）
    scenarios = []
    for data in scenario_data.values():
        mentions = len(data["post_ids"])
        if mentions >= min_mentions:
            top_issues = sorted(
                data["associated_issues"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            top_features = sorted(
                data["associated_features"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            scenarios.append({
                "label": data["label"],
                "heat": round(data["total_heat"], 1),
                "mentions": mentions,
                "associated_issues": [i[0] for i in top_issues],
                "associated_features": [f[0] for f in top_features],
                "post_ids": list(data["post_ids"]),
            })

    # 格式化人群输出（置信度过滤）
    audiences = []
    for data in audience_data.values():
        mentions = len(data["post_ids"])
        if mentions >= min_mentions:
            top_preferences = sorted(
                data["preferences"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            audiences.append({
                "label": data["label"],
                "heat": round(data["total_heat"], 1),
                "mentions": mentions,
                "preferences": [p[0] for p in top_preferences],
                "post_ids": list(data["post_ids"]),
            })

    # 按热度排序
    scenarios.sort(key=lambda x: x["heat"], reverse=True)
    audiences.sort(key=lambda x: x["heat"], reverse=True)

    # 记录派生结果
    logger.info(
        f"[场景人群派生] 从 {len(aggregated_entities)} 个实体派生: "
        f"场景 {len(scenarios)} 个, 人群 {len(audiences)} 个"
    )

    return {
        "scenarios": scenarios[:top_n],
        "audiences": audiences[:top_n],
    }


# ============================================================================
# KANO 需求分层 (§4.5.3) - 派生分析
# ============================================================================

def classify_kano_model(
    opinions_data: dict[str, list[dict[str, Any]]],
    mentions_threshold: int = 3,
    heat_threshold_percentile: float = 0.7,
) -> dict[str, list[dict[str, Any]]]:
    """KANO 需求分层分类

    基于聚合后的观点数据（话题级别）进行分类，与"热门观点"保持一致的数据源。

    分类规则 (§4.5.3)：
    - **基本型 (Must-be)**：High Mentions (普遍) + Negative Sentiment (痛点)
      → 来自 top_issues（负面观点话题）
    - **兴奋型 (Attractive)**：Low Mentions (稀缺) + High Heat (高共鸣) + Positive Sentiment
      → 来自 top_features 中低频高热度的正面话题
    - **期望型 (One-dimensional)**：High Mentions (普遍) + Positive Sentiment
      → 来自 top_features 中高频的正面话题

    Args:
        opinions_data: 观点数据 {"top_issues": [...], "top_features": [...]}
        mentions_threshold: 高频门槛（默认3次）
        heat_threshold_percentile: 高热度百分位（默认70%）

    Returns:
        dict: {
            "must_be": [...],  # 基本型需求（痛点）
            "attractive": [...],  # 兴奋型需求（惊喜）
            "one_dimensional": [...],  # 期望型需求（愿望）
        }
    """
    must_be = []
    attractive = []
    one_dimensional = []

    # 只使用观点聚合数据（话题级别），不混入实体级别的原始描述
    all_issues = opinions_data.get("top_issues", [])
    all_features = opinions_data.get("top_features", [])

    # 计算热度阈值（用于区分兴奋型需求）
    all_heats = [i.get("heat", 0) for i in all_issues + all_features]
    if all_heats:
        all_heats_sorted = sorted(all_heats)
        heat_threshold = all_heats_sorted[int(len(all_heats_sorted) * heat_threshold_percentile)]
    else:
        heat_threshold = 0

    # 1. Must-be (基本型)：高频 + 负面（来自 top_issues）
    for item in all_issues:
        mentions = item.get("mentions", 0)
        if mentions >= mentions_threshold:
            must_be.append({
                "label": item.get("topic", ""),
                "heat": item.get("heat", 0),
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
            })

    # 2. Attractive (兴奋型)：低频 + 高热度 + 正面
    for item in all_features:
        mentions = item.get("mentions", 0)
        heat = item.get("heat", 0)
        if mentions < mentions_threshold and heat >= heat_threshold:
            attractive.append({
                "label": item.get("topic", ""),
                "heat": heat,
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
            })

    # 3. One-dimensional (期望型)：高频 + 正面（来自 top_features）
    for item in all_features:
        mentions = item.get("mentions", 0)
        if mentions >= mentions_threshold:
            one_dimensional.append({
                "label": item.get("topic", ""),
                "heat": item.get("heat", 0),
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
            })

    # 按热度排序
    must_be.sort(key=lambda x: x["heat"], reverse=True)
    attractive.sort(key=lambda x: x["heat"], reverse=True)
    one_dimensional.sort(key=lambda x: x["heat"], reverse=True)

    return {
        "must_be": must_be[:10],
        "attractive": attractive[:10],
        "one_dimensional": one_dimensional[:10],
    }


# ============================================================================
# 竞品分析 (Competition Analysis)
# ============================================================================

def analyze_competition(
    entity_stats: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """分析竞品情况

    基于实体分类结果，计算竞品对比情感。

    Args:
        entity_stats: aggregate_entities 的返回结果

    Returns:
        dict: {
            "top_competitors": ["竞品A", "竞品B"],
            "comparison_sentiment": -0.2,  # 与竞品对比的相对情感
            "competitor_details": [...]
        }
    """
    target_entities = entity_stats.get("target_entities", [])
    competitor_entities = entity_stats.get("competitor_entities", [])

    # 计算本品平均情感
    target_sentiment = 0.0
    if target_entities:
        target_sentiment = sum(e.get("sentiment", 0) for e in target_entities) / len(target_entities)

    # 计算竞品平均情感
    competitor_sentiment = 0.0
    if competitor_entities:
        competitor_sentiment = sum(e.get("sentiment", 0) for e in competitor_entities) / len(competitor_entities)

    # 对比情感 = 本品情感 - 竞品情感
    # 正值 = 本品口碑更好，负值 = 竞品口碑更好
    comparison_sentiment = target_sentiment - competitor_sentiment if competitor_entities else 0.0

    # 提取竞品名称
    top_competitors = [e.get("name", "") for e in competitor_entities[:5]]

    # 竞品详情
    competitor_details = []
    for comp in competitor_entities[:5]:
        competitor_details.append({
            "name": comp.get("name", ""),
            "sentiment": comp.get("sentiment", 0),
            "sentiment_distribution": comp.get("sentiment_distribution", {"positive": 0, "negative": 0, "neutral": 0}),
            "heat": comp.get("heat", 0),
            "mentions": comp.get("mentions", 0),
            "post_ids": comp.get("post_ids", []),
            "top_features": comp.get("top_features", []),
            "top_issues": comp.get("top_issues", []),
        })

    return {
        "top_competitors": top_competitors,
        "comparison_sentiment": round(comparison_sentiment, 2),
        "target_sentiment": round(target_sentiment, 2),
        "competitor_sentiment": round(competitor_sentiment, 2),
        "competitor_details": competitor_details,
    }


# ============================================================================
# KOL 声音提取
# ============================================================================

def extract_kol_voices(
    posts_data: list[dict[str, Any]],
    db: Session,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """提取 KOL 声音

    KOL 定义：高影响力帖子的作者
    - 按 CII 排序，取 Top N 帖子
    - 提取作者、情感、摘要

    Args:
        posts_data: 帖子数据列表
        db: 数据库会话（用于获取作者信息）
        top_n: 返回前 N 个 KOL

    Returns:
        list: [{"author": "大V", "sentiment": 0.5, "summary": "...", "post_id": 123, "cii": 100}]
    """
    # 筛选有深度分析结果的帖子
    analyzed_posts = [
        p for p in posts_data
        if p.get("post_deep_result") and p.get("sentiment") is not None
    ]

    if not analyzed_posts:
        return []

    # 按 CII 排序
    sorted_posts = sorted(analyzed_posts, key=lambda x: x.get("cii", 0), reverse=True)

    # 获取帖子作者信息
    post_ids = [p["post_id"] for p in sorted_posts[:top_n * 2]]  # 多取一些以防重复作者

    # 查询帖子的作者信息
    stmt = select(SocialPost).where(SocialPost.id.in_(post_ids))
    posts = {p.id: p for p in db.execute(stmt).scalars().all()}

    # 构建 KOL 声音列表（去重作者）
    kol_voices = []
    seen_authors = set()

    for post_data in sorted_posts:
        if len(kol_voices) >= top_n:
            break

        post_id = post_data.get("post_id")
        post = posts.get(post_id)

        if not post:
            continue

        author = post.author_name or "匿名用户"

        # 跳过重复作者
        if author in seen_authors:
            continue
        seen_authors.add(author)

        # 获取摘要
        deep_result = post_data.get("post_deep_result") or {}
        summary = deep_result.get("summary", "")

        # 截断摘要
        if len(summary) > 100:
            summary = summary[:100] + "..."

        kol_voices.append({
            "author": author,
            "sentiment": post_data.get("sentiment", 0),
            "summary": summary,
            "post_id": post_id,
            "cii": round(post_data.get("cii", 0), 1),
        })

    return kol_voices
