"""任务级分析聚合器 (Task Analysis Aggregator)

在 Finalizer 中调用，对任务下的所有帖子分析结果进行聚合计算。

功能：
1. CII 互动指数计算
2. NSR 净情感率计算
3. SERP 健康度计算
4. 实体聚合与焦点地图
5. 四象限数据生成

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md
"""

import logging
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.social_media.analysis.models import PostAnalysis
from src.social_media.tasks.models import SocialPost

logger = logging.getLogger(__name__)


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

    Args:
        likes: 点赞数
        comments: 评论数
        shares: 分享/转发数
        collected: 收藏数

    Returns:
        float: CII 值，通常在 0-60 之间
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
# 营销浓度计算
# ============================================================================

def calculate_marketing_density(
    posts_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """计算营销浓度 (Marketing Density)

    规则：spam_score >= 4 的帖子被视为营销/推广内容

    Args:
        posts_data: 帖子数据列表，每个包含 spam_score 字段

    Returns:
        dict: {
            "promotion_ratio": 营销内容占比 (0-1),
            "organic_ratio": 自然内容占比 (0-1),
            "promotion_count": 营销帖子数,
            "organic_count": 自然帖子数,
        }
    """
    if not posts_data:
        return {
            "promotion_ratio": 0.0,
            "organic_ratio": 1.0,
            "promotion_count": 0,
            "organic_count": 0,
        }

    promotion_count = 0
    organic_count = 0

    for post in posts_data:
        spam_score = post.get("spam_score")
        if spam_score is None:
            continue  # 未筛选的帖子不计入

        if spam_score >= 4:
            promotion_count += 1
        else:
            organic_count += 1

    total = promotion_count + organic_count
    if total == 0:
        return {
            "promotion_ratio": 0.0,
            "organic_ratio": 1.0,
            "promotion_count": 0,
            "organic_count": 0,
        }

    return {
        "promotion_ratio": round(promotion_count / total, 3),
        "organic_ratio": round(organic_count / total, 3),
        "promotion_count": promotion_count,
        "organic_count": organic_count,
    }


# ============================================================================
# 舆论反差度计算
# ============================================================================

def calculate_sentiment_conflict(
    posts_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """计算舆论反差度 (Sentiment Conflict)

    比较帖子原文情感与评论情感的偏差，用于识别"翻车"风险。
    - 若帖子正面但评论负面 → 可能是软文翻车
    - 若帖子负面但评论正面 → 可能是逆袭口碑

    Args:
        posts_data: 帖子数据列表

    Returns:
        dict: {
            "avg_conflict": 平均反差度 (绝对值),
            "conflict_direction": 反差方向 ("post_positive" / "comment_positive" / "aligned"),
            "high_conflict_count": 高反差帖子数 (|差值| > 1),
            "risk_level": 风险等级 ("low" / "medium" / "high"),
        }
    """
    conflicts = []

    for post in posts_data:
        post_sentiment = post.get("sentiment")
        comment_deep_result = post.get("comment_deep_result") or {}

        # 从评论深度分析中获取聚合情感
        comment_sentiment = comment_deep_result.get("overall_sentiment")

        if post_sentiment is not None and comment_sentiment is not None:
            # 反差 = 帖子情感 - 评论情感
            # 正值: 帖子比评论正面
            # 负值: 评论比帖子正面
            conflict = post_sentiment - comment_sentiment
            conflicts.append({
                "post_id": post.get("post_id"),
                "post_sentiment": post_sentiment,
                "comment_sentiment": comment_sentiment,
                "conflict": conflict,
            })

    if not conflicts:
        return {
            "avg_conflict": 0.0,
            "conflict_direction": "aligned",
            "high_conflict_count": 0,
            "risk_level": "low",
        }

    # 计算平均反差（绝对值）
    avg_abs_conflict = sum(abs(c["conflict"]) for c in conflicts) / len(conflicts)

    # 计算平均反差（带方向）
    avg_conflict = sum(c["conflict"] for c in conflicts) / len(conflicts)

    # 高反差帖子数（差值绝对值 > 1）
    high_conflict_count = sum(1 for c in conflicts if abs(c["conflict"]) > 1)

    # 判断反差方向
    if avg_conflict > 0.3:
        conflict_direction = "post_positive"  # 帖子比评论正面（可能是软文）
    elif avg_conflict < -0.3:
        conflict_direction = "comment_positive"  # 评论比帖子正面（口碑逆袭）
    else:
        conflict_direction = "aligned"  # 基本一致

    # 风险等级判断
    high_conflict_ratio = high_conflict_count / len(conflicts) if conflicts else 0
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

def calculate_time_distribution(
    posts_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """计算时效性分布 (Time Distribution)

    统计帖子的发布时间分布，评估数据新鲜度。

    Args:
        posts_data: 帖子数据列表，每个包含 published_at 字段

    Returns:
        dict: {
            "distribution": [{"date": "2023-10-01", "count": 5}, ...],
            "freshness": {
                "last_7_days": 最近7天的帖子占比,
                "last_30_days": 最近30天的帖子占比,
                "avg_age_days": 平均发布天数,
            }
        }
    """
    from collections import Counter

    if not posts_data:
        return {
            "distribution": [],
            "freshness": {
                "last_7_days": 0.0,
                "last_30_days": 0.0,
                "avg_age_days": 0,
            }
        }

    now = datetime.now(timezone.utc)
    date_counts: Counter = Counter()
    ages_days = []

    for post in posts_data:
        published_at = post.get("published_at")
        if not published_at:
            continue

        # 处理不同格式的时间
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            except ValueError:
                continue
        elif not isinstance(published_at, datetime):
            continue

        # 确保有时区信息
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        # 统计日期分布
        date_str = published_at.strftime("%Y-%m-%d")
        date_counts[date_str] += 1

        # 计算天数
        age_days = (now - published_at).days
        ages_days.append(age_days)

    if not ages_days:
        return {
            "distribution": [],
            "freshness": {
                "last_7_days": 0.0,
                "last_30_days": 0.0,
                "avg_age_days": 0,
            }
        }

    # 生成分布数据（按日期排序）
    distribution = [
        {"date": date, "count": count}
        for date, count in sorted(date_counts.items())
    ]

    # 计算新鲜度指标
    total = len(ages_days)
    last_7_days = sum(1 for age in ages_days if age <= 7) / total
    last_30_days = sum(1 for age in ages_days if age <= 30) / total
    avg_age_days = sum(ages_days) / total

    return {
        "distribution": distribution[-30:],  # 最多返回30天数据
        "freshness": {
            "last_7_days": round(last_7_days, 3),
            "last_30_days": round(last_30_days, 3),
            "avg_age_days": round(avg_age_days, 1),
        }
    }


# ============================================================================
# NSR 净情感率计算
# ============================================================================

def calculate_nsr(
    posts_data: list[dict[str, Any]],
) -> float:
    """计算 NSR 净情感率 (Net Sentiment Rate)

    公式：NSR = Σ(Sentiment_i × CII_i) / Σ(CII_i)

    Args:
        posts_data: 帖子数据列表，每个包含 sentiment 和 cii 字段

    Returns:
        float: NSR 值，范围 [-2, +2]，>0 为正面，<0 为负面
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

def calculate_serp_health(
    posts_data: list[dict[str, Any]],
    top_n: int = 20,
) -> float:
    """计算 SERP 搜索健康度 (SERP Health Index)

    只计算 Top N 帖子的加权情感，衡量用户搜索时前排结果的"观感"。

    Args:
        posts_data: 帖子数据列表，需按互动量排序
        top_n: 取前多少条计算，默认 20

    Returns:
        float: SERP 健康度，范围 0-100
    """
    # 取 Top N
    top_posts = posts_data[:top_n]

    if not top_posts:
        return 50.0  # 无数据时返回中性值

    # 计算加权情感
    nsr = calculate_nsr(top_posts)

    # 将 [-2, +2] 映射到 [0, 100]
    # nsr = -2 → 0, nsr = 0 → 50, nsr = +2 → 100
    serp_health = (nsr + 2) / 4 * 100

    return round(serp_health, 1)


# ============================================================================
# 实体聚合与焦点地图
# ============================================================================

def _normalize_entity_name(name: str) -> str:
    """标准化实体名称（小写、去空格）"""
    return name.lower().strip()


def _are_similar_entities(name1: str, name2: str, threshold: float = 0.9) -> bool:
    """判断两个实体名称是否相似（用于合并）"""
    n1 = _normalize_entity_name(name1)
    n2 = _normalize_entity_name(name2)
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def aggregate_entities(
    posts_data: list[dict[str, Any]],
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """聚合任务内的实体，生成焦点地图

    处理逻辑：
    1. 实体对齐：合并相似度 > 0.9 的实体
    2. 聚合统计：TopicScore = Σ(Mentioned × CII)
    3. 排序：输出 Top N 实体及关联信息

    Args:
        posts_data: 帖子数据列表，每个包含 post_deep_result 和 cii
        top_n: 返回前多少个实体

    Returns:
        list: 实体聚合结果列表
    """
    # 收集所有实体及其出现信息
    entity_data: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "canonical_name": "",  # 标准化名称
        "type": "",
        "total_cii": 0.0,
        "mention_count": 0,
        "sentiment_sum": 0.0,
        "features": defaultdict(int),  # 特性出现次数
        "issues": defaultdict(int),  # 问题出现次数
        "post_ids": [],
    })

    # 实体名称映射（用于合并相似实体）
    name_mapping: dict[str, str] = {}

    def get_canonical_name(name: str) -> str:
        """获取实体的标准名称（可能已被映射到其他名称）"""
        normalized = _normalize_entity_name(name)
        if normalized in name_mapping:
            return name_mapping[normalized]

        # 检查是否与已有实体相似
        for existing_normalized, canonical in name_mapping.items():
            if _are_similar_entities(normalized, existing_normalized):
                name_mapping[normalized] = canonical
                return canonical

        # 新实体
        name_mapping[normalized] = normalized
        return normalized

    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 0)

        # 合并帖子深度分析和评论深度分析中的实体
        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        post_entities = post_deep_result.get("entities", [])
        comment_entities = comment_deep_result.get("entities", [])

        # 合并两个来源的实体（评论实体也用帖子的 CII 加权）
        all_entities = post_entities + comment_entities

        for entity in all_entities:
            entity_name = entity.get("name", "")
            if not entity_name:
                continue

            canonical = get_canonical_name(entity_name)
            data = entity_data[canonical]

            # 更新实体数据
            if not data["name"]:
                data["name"] = entity_name  # 保留原始名称（首次出现的）
                data["canonical_name"] = canonical
                data["type"] = entity.get("type", "其他")

            data["total_cii"] += cii
            data["mention_count"] += 1
            data["sentiment_sum"] += entity.get("sentiment", 0)

            if post_id:
                data["post_ids"].append(post_id)

            # 聚合特性和问题
            for feature in entity.get("features", []):
                if feature:
                    data["features"][feature] += 1
            for issue in entity.get("issues", []):
                if issue:
                    data["issues"][issue] += 1

    # 排序并生成结果
    sorted_entities = sorted(
        entity_data.values(),
        key=lambda x: x["total_cii"],
        reverse=True
    )[:top_n]

    result = []
    for entity in sorted_entities:
        if entity["mention_count"] == 0:
            continue

        avg_sentiment = entity["sentiment_sum"] / entity["mention_count"]

        # 取出现次数最多的特性和问题
        top_features = sorted(
            entity["features"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        top_issues = sorted(
            entity["issues"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        result.append({
            "name": entity["name"],
            "type": entity["type"],
            "heat": round(entity["total_cii"], 1),  # TopicScore
            "mention_count": entity["mention_count"],
            "avg_sentiment": round(avg_sentiment, 2),
            "top_features": [f[0] for f in top_features],
            "top_issues": [i[0] for i in top_issues],
        })

    return result


def aggregate_opinions(
    posts_data: list[dict[str, Any]],
    top_n: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """聚合任务内的观点，区分正面和负面

    Returns:
        dict: {"top_issues": [...], "top_features": [...]}
    """
    # 收集所有观点
    opinion_data: dict[str, dict] = defaultdict(lambda: {
        "category": "",
        "total_cii": 0.0,
        "sentiment_sum": 0.0,
        "count": 0,
        "opinions": defaultdict(int),  # 具体观点出现次数
    })

    for post in posts_data:
        cii = post.get("cii", 0)

        # 合并帖子深度分析和评论深度分析中的观点
        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        post_opinions = post_deep_result.get("general_opinions", [])
        comment_opinions = comment_deep_result.get("general_opinions", [])

        # 合并两个来源的观点（评论观点也用帖子的 CII 加权）
        all_opinions = post_opinions + comment_opinions

        for opinion in all_opinions:
            category = opinion.get("category", "其他")
            sentiment = opinion.get("sentiment", 0)

            data = opinion_data[category]
            data["category"] = category
            data["total_cii"] += cii
            data["sentiment_sum"] += sentiment
            data["count"] += 1

            for op in opinion.get("opinions", []):
                if op:
                    data["opinions"][op] += 1

    # 分类：正面 vs 负面
    issues = []  # 负面观点
    features = []  # 正面观点

    for data in opinion_data.values():
        if data["count"] == 0:
            continue

        avg_sentiment = data["sentiment_sum"] / data["count"]
        top_opinions = sorted(
            data["opinions"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        item = {
            "topic": data["category"],
            "heat": round(data["total_cii"], 1),
            "sentiment": round(avg_sentiment, 2),
            "summary": "; ".join([o[0] for o in top_opinions]) if top_opinions else "",
        }

        if avg_sentiment < -0.3:
            issues.append(item)
        elif avg_sentiment > 0.3:
            features.append(item)

    # 按热度排序
    issues.sort(key=lambda x: x["heat"], reverse=True)
    features.sort(key=lambda x: x["heat"], reverse=True)

    return {
        "top_issues": issues[:top_n],
        "top_features": features[:top_n],
    }


# ============================================================================
# 四象限数据生成
# ============================================================================

def generate_quadrant_data(
    posts_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成情感-互动四象限数据

    坐标系：
    - X轴：情感分 (-2 ~ +2)
    - Y轴：CII 互动指数

    区域定义：
    - Q1 爆雷区 (高互动/负面)：Sentiment < -0.5, CII > Avg(CII)
    - Q2 品牌区 (高互动/正面)：Sentiment > 0.5, CII > Avg(CII)
    - Q3 吐槽区 (低互动/负面)：Sentiment < -0.5, CII < Avg(CII)
    - Q4 自嗨区 (低互动/正面)：Sentiment > 0.5, CII < Avg(CII)

    Args:
        posts_data: 帖子数据列表

    Returns:
        list: 四象限数据点列表
    """
    if not posts_data:
        return []

    # 计算平均 CII
    total_cii = sum(p.get("cii", 0) for p in posts_data)
    avg_cii = total_cii / len(posts_data) if posts_data else 0

    quadrant_data = []

    for post in posts_data:
        sentiment = post.get("sentiment")
        cii = post.get("cii", 0)
        post_id = post.get("post_id")

        if sentiment is None:
            continue

        # 确定象限
        if sentiment < -0.5 and cii > avg_cii:
            quadrant = "Q1_danger"  # 爆雷区
        elif sentiment > 0.5 and cii > avg_cii:
            quadrant = "Q2_brand"  # 品牌区
        elif sentiment < -0.5 and cii <= avg_cii:
            quadrant = "Q3_complaint"  # 吐槽区
        elif sentiment > 0.5 and cii <= avg_cii:
            quadrant = "Q4_niche"  # 自嗨区
        else:
            quadrant = "neutral"  # 中性区

        # 获取标签（从深度分析结果中提取关键词）
        label = ""
        deep_result = post.get("post_deep_result") or {}
        summary = deep_result.get("summary", "")
        if summary:
            # 取摘要前20个字作为标签
            label = summary[:20] + "..." if len(summary) > 20 else summary

        quadrant_data.append({
            "post_id": post_id,
            "x": sentiment,  # 情感分
            "y": round(cii, 2),  # CII
            "quadrant": quadrant,
            "label": label,
        })

    return quadrant_data


def get_quadrant_summary(quadrant_data: list[dict[str, Any]]) -> dict[str, int]:
    """统计各象限的帖子数量"""
    summary = {
        "Q1_danger": 0,
        "Q2_brand": 0,
        "Q3_complaint": 0,
        "Q4_niche": 0,
        "neutral": 0,
    }

    for item in quadrant_data:
        quadrant = item.get("quadrant", "neutral")
        if quadrant in summary:
            summary[quadrant] += 1

    return summary


# ============================================================================
# 主聚合函数
# ============================================================================

def aggregate_task_analysis(
    db: Session,
    task_id: int,
) -> dict[str, Any]:
    """执行任务级分析聚合

    Args:
        db: 数据库会话
        task_id: 任务ID

    Returns:
        dict: 聚合结果，存入 AnalysisJob.result_data
    """
    logger.info(f"开始聚合任务 {task_id} 的分析结果")

    # 1. 查询所有帖子及其分析结果
    stmt = (
        select(SocialPost, PostAnalysis)
        .outerjoin(PostAnalysis, PostAnalysis.post_id == SocialPost.id)
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted == False)
    )
    result = db.execute(stmt)
    rows = result.all()

    if not rows:
        logger.warning(f"任务 {task_id} 没有帖子数据")
        return _empty_result()

    # 2. 准备聚合数据
    posts_data = []
    total_posts = 0
    screened_posts = 0
    deep_analyzed_posts = 0
    comment_analyzed_posts = 0

    for post, analysis in rows:
        total_posts += 1

        # 优先使用已保存的 CII，否则重新计算
        if analysis and analysis.cii is not None:
            cii = analysis.cii
        else:
            cii = calculate_cii_for_post(post)

        post_info = {
            "post_id": post.id,
            "cii": cii,
            "sentiment": None,
            "spam_score": None,  # 用于营销浓度计算
            "published_at": post.published_at,  # 用于时效性分布
            "post_deep_result": None,
            "comment_deep_result": None,
        }

        if analysis:
            if analysis.spam_score is not None:
                screened_posts += 1
                post_info["sentiment"] = analysis.sentiment
                post_info["spam_score"] = analysis.spam_score

            if analysis.post_deep_result:
                deep_analyzed_posts += 1
                post_info["post_deep_result"] = analysis.post_deep_result

            if analysis.comment_deep_result:
                comment_analyzed_posts += 1
                post_info["comment_deep_result"] = analysis.comment_deep_result

        posts_data.append(post_info)

    # 按 CII 排序（用于 SERP 计算）
    posts_data_sorted = sorted(posts_data, key=lambda x: x["cii"], reverse=True)

    # 3. 计算核心指标
    nsr = calculate_nsr(posts_data)
    avg_cii = sum(p["cii"] for p in posts_data) / len(posts_data) if posts_data else 0
    serp_health = calculate_serp_health(posts_data_sorted)

    # 4. 实体聚合
    entity_stats = aggregate_entities(posts_data)

    # 5. 观点聚合
    opinion_stats = aggregate_opinions(posts_data)

    # 6. 四象限数据
    quadrant_data = generate_quadrant_data(posts_data)
    quadrant_summary = get_quadrant_summary(quadrant_data)

    # 7. 组装结果
    result_data = {
        "meta": {
            "task_id": task_id,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "data_volume": {
                "total": total_posts,
                "screened": screened_posts,
                "deep_analyzed": deep_analyzed_posts,
                "comment_analyzed": comment_analyzed_posts,
            },
        },
        "metrics": {
            "nsr": round(nsr, 3),
            "avg_cii": round(avg_cii, 2),
            "serp_health": serp_health,
        },
        "charts": {
            "quadrant": quadrant_data[:50],  # 限制返回数量
            "quadrant_summary": quadrant_summary,
        },
        "insights": {
            "top_entities": entity_stats,
            "top_issues": opinion_stats.get("top_issues", []),
            "top_features": opinion_stats.get("top_features", []),
        },
    }

    logger.info(
        f"任务 {task_id} 聚合完成: "
        f"NSR={nsr:.3f}, AvgCII={avg_cii:.2f}, SERP={serp_health}"
    )

    return result_data


def _empty_result() -> dict[str, Any]:
    """返回空结果结构"""
    return {
        "meta": {
            "task_id": None,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "data_volume": {
                "total": 0,
                "screened": 0,
                "deep_analyzed": 0,
                "comment_analyzed": 0,
            },
        },
        "metrics": {
            "nsr": 0.0,
            "avg_cii": 0.0,
            "serp_health": 50.0,
        },
        "charts": {
            "quadrant": [],
            "quadrant_summary": {
                "Q1_danger": 0,
                "Q2_brand": 0,
                "Q3_complaint": 0,
                "Q4_niche": 0,
                "neutral": 0,
            },
        },
        "insights": {
            "top_entities": [],
            "top_issues": [],
            "top_features": [],
        },
    }
