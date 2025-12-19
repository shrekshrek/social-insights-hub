"""基础指标计算模块

包含 CII、NSR、SERP、营销浓度、舆论反差度等基础指标的计算逻辑。
"""

import math
from datetime import datetime, timezone
from typing import Any

from src.social_media.tasks.models import SocialPost


# ============================================================================
# CII 互动指数计算
# ============================================================================

def calculate_cii(
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    collected: int = 0,
) -> float:
    """计算单条内容的 CII 互动指数 (Content Interaction Index)

    公式：
    RawScore = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Collected × 3)
    CII = log10(RawScore + 1) × 10
    """
    raw_score = (
        (likes or 0) * 1 +
        (comments or 0) * 2 +
        (shares or 0) * 5 +
        (collected or 0) * 3
    )
    if raw_score <= 0:
        return 0.0
    return math.log10(raw_score + 1) * 10


def calculate_cii_for_post(post: SocialPost) -> float:
    """从帖子模型计算 CII"""
    return calculate_cii(
        likes=post.likes_count or 0,
        comments=post.comments_count or 0,
        shares=post.shares_count or 0,
        collected=post.collected_count or 0,
    )


# ============================================================================
# NSR 净情感率计算
# ============================================================================

def calculate_nsr(posts_data: list[dict[str, Any]]) -> float:
    """计算 NSR 净情感率 (Net Sentiment Rate)

    公式：NSR = Σ(Sentiment_i × CII_i) / Σ(CII_i)
    返回范围 [-2, +2]
    """
    total_weighted_sentiment = 0.0
    total_cii = 0.0

    for post in posts_data:
        sentiment = post.get("sentiment")
        cii = post.get("cii", 0)
        if sentiment is not None and cii > 0:
            total_weighted_sentiment += sentiment * cii
            total_cii += cii

    if total_cii == 0:
        return 0.0
    return total_weighted_sentiment / total_cii


# ============================================================================
# SERP 健康度计算
# ============================================================================

def calculate_serp_health(posts_data: list[dict[str, Any]], top_n: int = 20) -> float:
    """计算 SERP 搜索健康度，范围 0-100"""
    top_posts = posts_data[:top_n]
    if not top_posts:
        return 50.0

    nsr = calculate_nsr(top_posts)
    # [-2, +2] → [0, 100]
    return round((nsr + 2) / 4 * 100, 1)


# ============================================================================
# 营销浓度计算
# ============================================================================

def calculate_marketing_density(posts_data: list[dict[str, Any]]) -> dict[str, Any]:
    """计算营销浓度 (spam_score >= 4 视为营销内容)"""
    if not posts_data:
        return {"promotion_ratio": 0.0, "organic_ratio": 1.0, "promotion_count": 0, "organic_count": 0}

    promotion_count = 0
    organic_count = 0

    for post in posts_data:
        spam_score = post.get("spam_score")
        if spam_score is None:
            continue
        if spam_score >= 4:
            promotion_count += 1
        else:
            organic_count += 1

    total = promotion_count + organic_count
    if total == 0:
        return {"promotion_ratio": 0.0, "organic_ratio": 1.0, "promotion_count": 0, "organic_count": 0}

    return {
        "promotion_ratio": round(promotion_count / total, 3),
        "organic_ratio": round(organic_count / total, 3),
        "promotion_count": promotion_count,
        "organic_count": organic_count,
    }


# ============================================================================
# 舆论反差度计算
# ============================================================================

def calculate_sentiment_conflict(posts_data: list[dict[str, Any]]) -> dict[str, Any]:
    """计算舆论反差度 (帖子情感 vs 评论情感)"""
    conflicts = []

    for post in posts_data:
        post_sentiment = post.get("sentiment")
        comment_deep_result = post.get("comment_deep_result") or {}
        comment_sentiment = comment_deep_result.get("overall_sentiment")

        if post_sentiment is not None and comment_sentiment is not None:
            conflict = post_sentiment - comment_sentiment
            conflicts.append({"conflict": conflict})

    if not conflicts:
        return {"avg_conflict": 0.0, "conflict_direction": "aligned", "high_conflict_count": 0, "risk_level": "low"}

    avg_abs_conflict = sum(abs(c["conflict"]) for c in conflicts) / len(conflicts)
    avg_conflict = sum(c["conflict"] for c in conflicts) / len(conflicts)
    high_conflict_count = sum(1 for c in conflicts if abs(c["conflict"]) > 1)

    # 反差方向
    if avg_conflict > 0.3:
        conflict_direction = "post_positive"
    elif avg_conflict < -0.3:
        conflict_direction = "comment_positive"
    else:
        conflict_direction = "aligned"

    # 风险等级
    high_conflict_ratio = high_conflict_count / len(conflicts)
    if avg_abs_conflict > 1.0 or high_conflict_ratio > 0.3:
        risk_level = "high"
    elif avg_abs_conflict > 0.5 or high_conflict_ratio > 0.15:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "avg_conflict": round(avg_abs_conflict, 3),
        "conflict_direction": conflict_direction,
        "high_conflict_count": high_conflict_count,
        "risk_level": risk_level,
    }


# ============================================================================
# 时效性分布统计
# ============================================================================

def calculate_time_distribution(posts_data: list[dict[str, Any]]) -> dict[str, Any]:
    """计算时效性分布"""
    if not posts_data:
        return {"distribution": [], "freshness": {"last_7_days": 0.0, "last_30_days": 0.0, "avg_age_days": 0}, "skipped_count": 0}

    now = datetime.now(timezone.utc)
    date_posts: dict[str, list[int]] = {}  # 日期 -> 帖子ID列表
    ages_days = []
    skipped_count = 0  # 跳过的帖子数（无发布时间）

    for post in posts_data:
        published_at = post.get("published_at")
        post_id = post.get("post_id")
        if not published_at:
            skipped_count += 1
            continue

        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            except ValueError:
                continue
        elif not isinstance(published_at, datetime):
            continue

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        date_str = published_at.strftime("%Y-%m-%d")
        if date_str not in date_posts:
            date_posts[date_str] = []
        if post_id:
            date_posts[date_str].append(post_id)
        age_days = (now - published_at).days
        ages_days.append(age_days)

    if not ages_days:
        return {"distribution": [], "freshness": {"last_7_days": 0.0, "last_30_days": 0.0, "avg_age_days": 0}, "skipped_count": skipped_count}

    distribution = [
        {"date": date, "count": len(post_ids), "post_ids": post_ids}
        for date, post_ids in sorted(date_posts.items())
    ]
    total = len(ages_days)

    return {
        "distribution": distribution,  # 返回全量数据，不再截断
        "freshness": {
            "last_7_days": round(sum(1 for age in ages_days if age <= 7) / total, 3),
            "last_30_days": round(sum(1 for age in ages_days if age <= 30) / total, 3),
            "avg_age_days": round(sum(ages_days) / total, 1),
        },
        "skipped_count": skipped_count  # 跳过的帖子数（无发布时间）
    }
