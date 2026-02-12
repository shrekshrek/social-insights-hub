"""广告/有机内容对比分析模块 (Spam Comparison)

按 spam_score 阈值将帖子分为高广告组和低广告组，
分别对原文深度分析和评论深度分析进行轻量聚合，
输出 4 块对比数据供前端展示。

4 块结构：
- high_spam.post_analysis:    高广告帖的原文分析（广告在说什么）
- high_spam.comment_analysis: 高广告帖的评论分析（用户对广告的反馈）
- low_spam.post_analysis:     低广告帖的原文分析（真实用户在说什么）
- low_spam.comment_analysis:  低广告帖的评论分析（自然讨论中的用户反馈）
"""

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# 默认阈值：spam_score >= 6 视为高广告内容
DEFAULT_SPAM_COMPARISON_THRESHOLD = 6.0


def build_spam_comparison(
    posts_data: list[dict[str, Any]],
    threshold: float = DEFAULT_SPAM_COMPARISON_THRESHOLD,
) -> dict[str, Any]:
    """构建广告/有机内容的 4 块对比分析

    Args:
        posts_data: 帖子数据列表（含 spam_score, post_deep_result, comment_deep_result）
        threshold: 广告分阈值，>= 此值为高广告组

    Returns:
        dict: 对比分析结果
    """
    # 只处理已完成初筛的帖子
    screened = [p for p in posts_data if p.get("spam_score") is not None]

    high_spam = [p for p in screened if p["spam_score"] >= threshold]
    low_spam = [p for p in screened if p["spam_score"] < threshold]

    logger.info(
        f"[Spam对比] 阈值={threshold}, "
        f"高广告={len(high_spam)}条, 低广告={len(low_spam)}条 "
        f"(共{len(screened)}条已初筛)"
    )

    return {
        "config": {"threshold": threshold},
        "high_spam": _build_group_analysis(high_spam),
        "low_spam": _build_group_analysis(low_spam),
    }


def _build_group_analysis(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """对一组帖子进行轻量聚合分析"""
    if not posts:
        return _empty_group()

    post_count = len(posts)
    avg_cii = sum(p.get("cii", 0) for p in posts) / post_count

    sentiments = [p["sentiment"] for p in posts if p.get("sentiment") is not None]
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

    deep_count = sum(1 for p in posts if p.get("post_deep_result"))
    comment_count = sum(1 for p in posts if p.get("comment_deep_result"))

    # 4 块中的 2 块：原文深度 + 评论深度
    post_entities, post_opinions = _collect_from_deep_results(
        posts, "post_deep_result"
    )
    comment_entities, comment_opinions = _collect_from_deep_results(
        posts, "comment_deep_result"
    )

    return {
        "post_count": post_count,
        "deep_analyzed_count": deep_count,
        "comment_analyzed_count": comment_count,
        "metrics": {
            "avg_cii": round(avg_cii, 2),
            "avg_sentiment": round(avg_sentiment, 2),
        },
        "post_analysis": {
            "top_entities": post_entities[:10],
            "top_opinions": post_opinions[:10],
        },
        "comment_analysis": {
            "top_entities": comment_entities[:10],
            "top_opinions": comment_opinions[:10],
        },
    }


def _collect_from_deep_results(
    posts: list[dict[str, Any]],
    result_key: str,
) -> tuple[list[dict], list[dict]]:
    """从深度分析结果中收集实体和观点

    Args:
        posts: 帖子数据列表
        result_key: "post_deep_result" 或 "comment_deep_result"

    Returns:
        (entities_list, opinions_list) 按 mentions 降序排列
    """
    entity_map: dict[str, dict] = {}
    opinion_map: dict[str, dict] = {}

    for post in posts:
        deep = post.get(result_key) or {}

        # 实体收集
        for entity in deep.get("entities", []):
            name = entity.get("name", "")
            if not name:
                continue

            if name not in entity_map:
                entity_map[name] = {
                    "name": name,
                    "type": entity.get("type", "其他"),
                    "count": 0,
                    "sentiment_sum": 0,
                    "features": Counter(),
                    "issues": Counter(),
                }

            em = entity_map[name]
            em["count"] += 1
            em["sentiment_sum"] += entity.get("sentiment", 0)

            for f in entity.get("features", []):
                if f:
                    em["features"][f] += 1
            for i in entity.get("issues", []):
                if i:
                    em["issues"][i] += 1

        # 观点收集
        for opinion in deep.get("general_opinions", []):
            cat = opinion.get("category", "")
            if not cat:
                continue

            if cat not in opinion_map:
                opinion_map[cat] = {
                    "category": cat,
                    "count": 0,
                    "sentiment_sum": 0,
                    "sample_opinions": [],
                }

            om = opinion_map[cat]
            om["count"] += 1
            om["sentiment_sum"] += opinion.get("sentiment", 0)

            for op in opinion.get("opinions", []):
                if len(om["sample_opinions"]) < 5 and op not in om["sample_opinions"]:
                    om["sample_opinions"].append(op)

    # 格式化实体
    entities = []
    for em in entity_map.values():
        avg_sent = em["sentiment_sum"] / em["count"] if em["count"] > 0 else 0
        entities.append(
            {
                "name": em["name"],
                "type": em["type"],
                "mentions": em["count"],
                "sentiment": round(avg_sent, 2),
                "top_features": [f for f, _ in em["features"].most_common(5)],
                "top_issues": [i for i, _ in em["issues"].most_common(5)],
            }
        )
    entities.sort(key=lambda x: x["mentions"], reverse=True)

    # 格式化观点
    opinions = []
    for om in opinion_map.values():
        avg_sent = om["sentiment_sum"] / om["count"] if om["count"] > 0 else 0
        opinions.append(
            {
                "category": om["category"],
                "mentions": om["count"],
                "sentiment": round(avg_sent, 2),
                "sample_opinions": om["sample_opinions"],
            }
        )
    opinions.sort(key=lambda x: x["mentions"], reverse=True)

    return entities, opinions


def _empty_group() -> dict[str, Any]:
    """空组结果"""
    return {
        "post_count": 0,
        "deep_analyzed_count": 0,
        "comment_analyzed_count": 0,
        "metrics": {
            "avg_cii": 0,
            "avg_sentiment": 0,
        },
        "post_analysis": {
            "top_entities": [],
            "top_opinions": [],
        },
        "comment_analysis": {
            "top_entities": [],
            "top_opinions": [],
        },
    }
