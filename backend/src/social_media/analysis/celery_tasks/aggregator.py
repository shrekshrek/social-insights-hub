"""任务级分析聚合器 (Task Analysis Aggregator)

在 Finalizer 中调用，对任务下的所有帖子分析结果进行聚合计算。

注意：本项目采用双重情感评分体系（详见设计文档 §1.1）
- 宏观指标 (NSR, SERP, 四象限): 基于初筛情感 (-2 ~ +2)
- 微观指标 (实体, 观点, KANO): 基于深度分析情感 (-1 ~ +1)

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
from collections import defaultdict, Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.social_media.analysis.models import PostAnalysis
from src.social_media.tasks.models import SocialPost, DataTask

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
# 主体一致性过滤 (Subject Consistency)
# ============================================================================

def _normalize_entity_name(name: str) -> str:
    """标准化实体名称（小写、去空格）"""
    return name.lower().strip()


def _are_similar_entities(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """判断两个实体名称是否相似（用于合并）"""
    n1 = _normalize_entity_name(name1)
    n2 = _normalize_entity_name(name2)
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def _contains_keyword(entity_name: str, keywords: list[str]) -> bool:
    """检查实体名称是否包含任一关键词（忽略大小写）"""
    normalized_name = _normalize_entity_name(entity_name)
    for keyword in keywords:
        normalized_keyword = _normalize_entity_name(keyword)
        if normalized_keyword in normalized_name or normalized_name in normalized_keyword:
            return True
    return False


def classify_entity_role(
    entity_name: str,
    entity_data: dict[str, Any],
    task_keywords: list[str],
    competitor_names: set[str],
) -> str:
    """对实体进行主体角色分类

    分类规则 (§4.3)：
    1. Target: 实体名称包含任务关键词 → 本品
    2. Competitor: 实体名称在竞品列表中 → 竞品
    3. Other: 其他实体（人物、场景、技术术语等，不是噪音）

    注意：role 与 type 是两个独立维度
    - type: 实体类型（品牌/产品/服务/人物/其他）
    - role: 主体角色（target/competitor/other）

    Args:
        entity_name: 实体名称
        entity_data: 实体数据（包含 competitors 字段）
        task_keywords: 任务关键词列表
        competitor_names: 已识别的竞品名称集合

    Returns:
        str: "target" / "competitor" / "other"
    """
    # 规则 1: 包含任务关键词 → Target (本品)
    if _contains_keyword(entity_name, task_keywords):
        return "target"

    # 规则 2: 在竞品列表中 → Competitor (竞品)
    normalized_name = _normalize_entity_name(entity_name)
    for comp_name in competitor_names:
        if _are_similar_entities(normalized_name, comp_name, threshold=0.8):
            return "competitor"

    # 规则 3: 其他实体 → Other (非本品/竞品，但可能是有价值的上下文)
    return "other"


def extract_competitor_names(
    entities_data: dict[str, dict],
    task_keywords: list[str],
) -> set[str]:
    """从 Target 实体的 competitors 字段提取竞品名称

    Args:
        entities_data: 所有实体数据
        task_keywords: 任务关键词

    Returns:
        set: 竞品名称集合（已标准化）
    """
    competitor_names: set[str] = set()

    for canonical, data in entities_data.items():
        entity_name = data.get("name", "")

        # 仅从 Target 实体中提取
        if _contains_keyword(entity_name, task_keywords):
            # 从实体的 competitors 字段提取
            competitors = data.get("competitors", [])
            for comp in competitors:
                if comp:
                    competitor_names.add(_normalize_entity_name(comp))

    return competitor_names


# ============================================================================
# 实体聚合与焦点地图（支持来源标记）
# ============================================================================


def aggregate_entities(
    posts_data: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    """聚合任务内的实体，生成焦点地图

    处理逻辑 (§4.3)：
    1. 实体对齐：合并相似度 > 0.8 的实体
    2. 情感分组：按 (entity_name, sentiment) 组合分组，避免混淆正负面评价
    3. 来源标记：区分来自 Post 还是 Comment
    4. 主体过滤：分类为 Target / Competitor / Other
    5. 双重加权：Heat (Σ CII) 和 Mentions (Unique Posts)
    6. 排序：输出 Top N 实体及关联信息

    数据结构说明：
    - key: canonical_name（只按实体名称分组，不按情感分组）
    - sentiment_sum/sentiment_count: 用于计算派生情感值
    - post_ids: 所有涉及该实体的帖子ID集合（用于计算 mentions）
    - post_sources: 从帖子原文中提取该实体的帖子ID集合
    - comment_sources: 从评论中提取该实体的帖子ID集合
    - cii_added_posts: 已贡献CII的帖子ID（避免同一帖子重复累加CII）

    设计理念：
    - 实体的情感倾向不是独立维度，而是 features/issues 的对比结果
    - 同一实体的正面/负面评价应该合并展示，给用户完整画像
    - 派生情感值 = Σ(sentiment * cii) / Σ cii（CII加权情感）

    Args:
        posts_data: 帖子数据列表，每个包含 post_deep_result 和 cii
        task_keywords: 任务关键词列表，用于主体过滤
        top_n: 返回前多少个实体

    Returns:
        dict: {
            "top_entities": 热度排名前N的实体列表（展示用）,
            "target_entities": 本品实体列表,
            "competitor_entities": 竞品实体列表,
            "aggregated_entities": 完整融合数据（用于项目级分析）,
        }
    """
    task_keywords = task_keywords or []

    # 收集所有实体及其出现信息
    # key 格式: canonical_name（只按实体名称分组，不按情感分组）
    entity_data: dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "canonical_name": "",
        "type": "",
        # 情感派生计算：sentiment_weighted_sum / total_cii
        "sentiment_weighted_sum": 0.0,  # Σ(sentiment * cii)，用于计算加权情感
        "positive_count": 0,   # 正面提及次数
        "negative_count": 0,   # 负面提及次数
        "neutral_count": 0,    # 中性提及次数
        "total_cii": 0.0,
        "cii_added_posts": set(),  # 已贡献CII的帖子（避免重复累加）
        "post_sources": set(),  # 从帖子原文提取的帖子ID
        "comment_sources": set(),  # 从评论提取的帖子ID
        "post_ids": set(),  # 所有涉及的帖子ID（用于计算 mentions）
        # 实体维度信息（完整聚合，用于项目级分析）
        # 使用 defaultdict(set) 记录每个维度项来源的帖子ID，支持追溯
        "features": defaultdict(set),       # 特性/功能/优点 -> post_ids
        "issues": defaultdict(set),         # 问题/缺点/不满 -> post_ids
        "expectations": defaultdict(set),   # 改进期望/建议 -> post_ids
        "audience": defaultdict(set),       # 目标人群 -> post_ids
        "scenarios": defaultdict(set),      # 使用场景/用途 -> post_ids
        "market_factors": defaultdict(set), # 价格/促销/渠道 -> post_ids
        "competitors": defaultdict(set),    # 竞品对比 -> post_ids
    })

    # 实体名称映射（用于合并相似实体）
    name_mapping: dict[str, str] = {}
    # 记录合并的实体对
    merged_pairs: list[tuple[str, str, float]] = []

    def get_canonical_name(name: str) -> str:
        """获取实体的标准名称（可能已被映射到其他名称）"""
        normalized = _normalize_entity_name(name)
        if normalized in name_mapping:
            return name_mapping[normalized]

        # 检查是否与已有实体相似
        for existing_normalized, canonical in name_mapping.items():
            similarity = SequenceMatcher(None, normalized, existing_normalized).ratio()
            if similarity >= 0.8:
                name_mapping[normalized] = canonical
                # 记录合并对
                merged_pairs.append((name, canonical, similarity))
                return canonical

        # 新实体
        name_mapping[normalized] = normalized
        return normalized

    def process_entity(entity: dict, post_id: int, cii: float, source: str):
        """处理单个实体，只按 canonical_name 分组（不按情感分组）"""
        entity_name = entity.get("name", "")
        if not entity_name:
            return

        canonical = get_canonical_name(entity_name)
        sentiment = entity.get("sentiment", 0)

        # 只使用 canonical 作为 key（不再按情感分组）
        key = canonical
        data = entity_data[key]

        # 更新实体基本信息
        if not data["name"]:
            data["name"] = entity_name
            data["canonical_name"] = canonical
            data["type"] = entity.get("type", "其他")

        # 统计情感分布
        if sentiment == 1:
            data["positive_count"] += 1
        elif sentiment == -1:
            data["negative_count"] += 1
        else:
            data["neutral_count"] += 1

        # CII 只累加一次（每个帖子对每个实体只贡献一次）
        if post_id and post_id not in data["cii_added_posts"]:
            data["total_cii"] += cii
            data["sentiment_weighted_sum"] += sentiment * cii  # 加权情感累加
            data["cii_added_posts"].add(post_id)

        # 来源标记（使用集合去重）
        if post_id:
            if source == "post":
                data["post_sources"].add(post_id)
            else:
                data["comment_sources"].add(post_id)
            data["post_ids"].add(post_id)

        # 聚合所有维度信息（记录来源帖子ID，支持追溯）
        if post_id:
            for feature in entity.get("features", []):
                if feature:
                    data["features"][feature].add(post_id)
            for issue in entity.get("issues", []):
                if issue:
                    data["issues"][issue].add(post_id)
            for expectation in entity.get("expectations", []):
                if expectation:
                    data["expectations"][expectation].add(post_id)
            for aud in entity.get("audience", []):
                if aud:
                    data["audience"][aud].add(post_id)
            for scenario in entity.get("scenarios", []):
                if scenario:
                    data["scenarios"][scenario].add(post_id)
            for factor in entity.get("market_factors", []):
                if factor:
                    data["market_factors"][factor].add(post_id)
            for comp in entity.get("competitors", []):
                if comp:
                    data["competitors"][comp].add(post_id)

    # 遍历所有帖子
    raw_entity_count = 0  # 统计原始实体数量
    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 0)

        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        # 处理帖子实体（标记来源为 post）
        post_entities = post_deep_result.get("entities", [])
        raw_entity_count += len(post_entities)
        for entity in post_entities:
            process_entity(entity, post_id, cii, "post")

        # 处理评论实体（标记来源为 comment）
        comment_entities = comment_deep_result.get("entities", [])
        raw_entity_count += len(comment_entities)
        for entity in comment_entities:
            process_entity(entity, post_id, cii, "comment")

    # 记录聚合效果
    merged_entity_count = len(entity_data)
    if raw_entity_count > 0:
        print(
            f"[实体聚合] 按 canonical_name 分组: "
            f"原始 {raw_entity_count} 个 -> 分组后 {merged_entity_count} 个实体"
        )
        # 输出相似度合并详情
        if merged_pairs:
            print(f"[实体聚合] 名称相似度合并 ({len(merged_pairs)} 对):")
            for new_name, canonical, similarity in merged_pairs[:5]:
                print(f"  '{new_name}' -> '{canonical}' (相似度: {similarity:.2f})")
    else:
        print("[实体聚合] 无实体数据")

    # 提取竞品名称
    competitor_names = extract_competitor_names(entity_data, task_keywords)

    # 对实体进行角色分类并格式化输出
    def format_entity(data: dict) -> dict:
        mentions = len(data["post_ids"])
        if mentions == 0:
            return None

        post_source_count = len(data["post_sources"])
        comment_source_count = len(data["comment_sources"])
        total_source_count = post_source_count + comment_source_count

        # 来源分布（基于唯一帖子数）
        source_distribution = {
            "post": round(post_source_count / total_source_count, 2) if total_source_count > 0 else 0,
            "comment": round(comment_source_count / total_source_count, 2) if total_source_count > 0 else 0,
        }

        # 派生情感值：Σ(sentiment * cii) / Σ cii
        # 范围 [-1, 1]，正值偏正面，负值偏负面
        derived_sentiment = 0.0
        if data["total_cii"] > 0:
            derived_sentiment = round(data["sentiment_weighted_sum"] / data["total_cii"], 2)

        # 情感分布（用于展示正/负/中性提及比例）
        total_sentiment_count = data["positive_count"] + data["negative_count"] + data["neutral_count"]
        sentiment_distribution = {
            "positive": data["positive_count"],
            "negative": data["negative_count"],
            "neutral": data["neutral_count"],
        }

        # 角色分类
        role = classify_entity_role(
            data["name"],
            data,
            task_keywords,
            competitor_names,
        )

        top_features = sorted(
            data["features"].items(),
            key=lambda x: len(x[1]),  # 按帖子数排序
            reverse=True
        )[:5]
        top_issues = sorted(
            data["issues"].items(),
            key=lambda x: len(x[1]),  # 按帖子数排序
            reverse=True
        )[:5]
        top_expectations = sorted(
            data["expectations"].items(),
            key=lambda x: len(x[1]),  # 按帖子数排序
            reverse=True
        )[:5]

        return {
            "name": data["name"],
            "type": data["type"],
            "role": role,  # target / competitor / other
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,  # 唯一帖子数
            "sentiment": derived_sentiment,  # 派生情感值 [-1, 1]
            "sentiment_distribution": sentiment_distribution,  # 情感分布
            "source_distribution": source_distribution,
            "top_features": [f[0] for f in top_features],
            "top_issues": [i[0] for i in top_issues],
            "top_expectations": [e[0] for e in top_expectations],
            "post_ids": list(data["post_ids"]),  # 添加帖子ID用于反向追溯
        }

    # 格式化所有实体
    formatted_entities = []
    for data in entity_data.values():
        formatted = format_entity(data)
        if formatted:
            formatted_entities.append(formatted)

    # 按 Heat 排序
    formatted_entities.sort(key=lambda x: x["heat"], reverse=True)

    # 分类输出（展示用 TOP N）
    top_entities = formatted_entities[:top_n]
    target_entities = [e for e in formatted_entities if e["role"] == "target"][:top_n]
    competitor_entities = [e for e in formatted_entities if e["role"] == "competitor"][:top_n]

    # 构建完整融合数据（用于项目级分析）
    aggregated_entities = {}
    for key, data in entity_data.items():
        mentions = len(data["post_ids"])
        if mentions == 0:
            continue
        # 派生情感值
        derived_sentiment = 0.0
        if data["total_cii"] > 0:
            derived_sentiment = round(data["sentiment_weighted_sum"] / data["total_cii"], 2)
        aggregated_entities[key] = {
            "name": data["name"],
            "canonical_name": data["canonical_name"],
            "type": data["type"],
            "sentiment": derived_sentiment,  # 派生情感值 [-1, 1]
            "sentiment_distribution": {
                "positive": data["positive_count"],
                "negative": data["negative_count"],
                "neutral": data["neutral_count"],
            },
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,
            "post_source_count": len(data["post_sources"]),
            "comment_source_count": len(data["comment_sources"]),
            "post_ids": list(data["post_ids"]),
            # 完整的维度信息（带帖子追溯，用于项目级再融合）
            "features": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["features"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "issues": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["issues"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "expectations": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["expectations"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "audience": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["audience"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "scenarios": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["scenarios"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "market_factors": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["market_factors"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
            "competitors": [
                {"text": text, "post_ids": list(post_ids)}
                for text, post_ids in sorted(data["competitors"].items(), key=lambda x: len(x[1]), reverse=True)
            ],
        }

    return {
        "top_entities": top_entities,  # 展示用 TOP N
        "target_entities": target_entities,
        "competitor_entities": competitor_entities,
        "aggregated_entities": aggregated_entities,  # 完整融合数据
    }


def aggregate_opinions(
    posts_data: list[dict[str, Any]],
    top_n: int = 10,
) -> dict[str, Any]:
    """聚合任务内的观点，按 (category, sentiment) 分组融合，避免混淆不同情感的观点

    改进点：
    - 原方案：按 category 融合所有情感，最后按平均情感分类
    - 新方案：按 (category, sentiment) 组合融合，同一话题不同情感的观点分开存储

    数据结构说明：
    - post_ids: 所有涉及该话题的帖子ID集合（用于计算 mentions）
    - post_sources: 从帖子原文中提取该观点的帖子ID集合
    - comment_sources: 从评论中提取该观点的帖子ID集合
    - cii_added_posts: 已贡献CII的帖子ID（避免同一帖子重复累加CII）
    - opinions: 具体观点文本 -> 包含该观点的帖子ID集合

    Returns:
        dict: {
            "top_issues": [...],  # 负面观点 TOP N
            "top_features": [...],  # 正面观点 TOP N
            "aggregated_opinions": {...}  # 原始融合数据，用于持久化和项目级分析
        }
    """
    # 按 (category, sentiment) 组合收集观点
    # key 格式: "category|sentiment" 如 "价格|1", "价格|-1", "价格|0"
    opinion_data: dict[str, dict] = defaultdict(lambda: {
        "category": "",
        "sentiment": 0,  # 固定的情感值 (-1, 0, 1)
        "total_cii": 0.0,
        "cii_added_posts": set(),  # 已贡献CII的帖子（避免重复累加）
        "post_sources": set(),  # 从帖子原文提取的帖子ID
        "comment_sources": set(),  # 从评论提取的帖子ID
        "post_ids": set(),  # 所有涉及的帖子ID（用于计算 mentions）
        "opinions": defaultdict(set),  # 观点文本 -> 帖子ID集合
    })

    def process_opinions(opinions: list, post_id: int, cii: float, source: str):
        """处理观点列表，按 (category, sentiment) 分组"""
        for opinion in opinions:
            category = opinion.get("category", "其他")
            sentiment = opinion.get("sentiment", 0)

            # 使用 category|sentiment 作为 key
            key = f"{category}|{sentiment}"
            data = opinion_data[key]
            data["category"] = category
            data["sentiment"] = sentiment  # 保留原始情感值

            # CII 只累加一次（每个帖子对每个分组只贡献一次）
            if post_id and post_id not in data["cii_added_posts"]:
                data["total_cii"] += cii
                data["cii_added_posts"].add(post_id)

            # 来源标记（使用集合去重）
            if post_id:
                if source == "post":
                    data["post_sources"].add(post_id)
                else:
                    data["comment_sources"].add(post_id)
                data["post_ids"].add(post_id)

            for op in opinion.get("opinions", []):
                if op and post_id:
                    data["opinions"][op].add(post_id)

    for post in posts_data:
        post_id = post.get("post_id")
        cii = post.get("cii", 0) or 0

        post_deep_result = post.get("post_deep_result") or {}
        comment_deep_result = post.get("comment_deep_result") or {}

        # 分别处理帖子和评论的观点
        process_opinions(
            post_deep_result.get("general_opinions", []),
            post_id, cii, "post"
        )
        process_opinions(
            comment_deep_result.get("general_opinions", []),
            post_id, cii, "comment"
        )

    # 构建结果
    issues = []  # 负面观点 (sentiment == -1)
    features = []  # 正面观点 (sentiment == 1)
    aggregated_opinions = {}  # 原始融合数据（用于持久化）

    for key, data in opinion_data.items():
        mentions = len(data["post_ids"])
        if mentions == 0:
            continue

        post_source_count = len(data["post_sources"])
        comment_source_count = len(data["comment_sources"])
        total_source_count = post_source_count + comment_source_count

        # 来源分布（基于唯一帖子数）
        source_distribution = {
            "post": round(post_source_count / total_source_count, 2) if total_source_count > 0 else 0,
            "comment": round(comment_source_count / total_source_count, 2) if total_source_count > 0 else 0,
        }

        # 按帖子数排序（保留全部观点用于项目级分析）
        all_opinions = sorted(
            data["opinions"].items(),
            key=lambda x: len(x[1]),  # 按包含该观点的帖子数排序
            reverse=True
        )

        # 保存原始融合数据（每个观点带 post_ids，保留全部）
        aggregated_opinions[key] = {
            "category": data["category"],
            "sentiment": data["sentiment"],
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,
            "post_source_count": post_source_count,
            "comment_source_count": comment_source_count,
            "post_ids": list(data["post_ids"]),
            "opinions": [  # 全部观点（用于项目级分析）
                {
                    "text": op_text,
                    "post_ids": list(op_post_ids),
                }
                for op_text, op_post_ids in all_opinions
            ],
        }

        # 构建展示用的 item（也带 post_ids 用于反向追溯）
        item = {
            "topic": data["category"],
            "heat": round(data["total_cii"], 1),
            "mentions": mentions,
            "sentiment": data["sentiment"],  # 直接使用原始情感值
            "source_distribution": source_distribution,
            "top_opinions": [op[0] for op in all_opinions[:3]] if all_opinions else [],
            "post_ids": list(data["post_ids"]),  # 该话题涉及的帖子
        }

        # 按原始情感值分类（不再用平均值判断）
        if data["sentiment"] == -1:
            issues.append(item)
        elif data["sentiment"] == 1:
            features.append(item)
        # sentiment == 0 的中性观点暂不展示

    # 按热度排序
    issues.sort(key=lambda x: x["heat"], reverse=True)
    features.sort(key=lambda x: x["heat"], reverse=True)

    # 记录聚合效果
    total_keys = len(aggregated_opinions)
    positive_count = len([k for k in aggregated_opinions if k.endswith("|1")])
    negative_count = len([k for k in aggregated_opinions if k.endswith("|-1")])
    neutral_count = len([k for k in aggregated_opinions if k.endswith("|0")])
    print(
        f"[观点聚合] 按 (category, sentiment) 分组: "
        f"总计 {total_keys} 个 (正面 {positive_count}, 负面 {negative_count}, 中性 {neutral_count})"
    )
    if aggregated_opinions:
        print("[观点聚合] 前5个分组示例:")
        for i, (key, data) in enumerate(list(aggregated_opinions.items())[:5]):
            first_op = data['opinions'][0] if data['opinions'] else None
            op_info = f", 首个观点='{first_op['text']}'({len(first_op['post_ids'])}帖)" if first_op else ""
            print(f"  {key}: 热度={data['heat']}, 提及={data['mentions']}帖, 观点数={len(data['opinions'])}{op_info}")

    return {
        "top_issues": issues[:top_n],
        "top_features": features[:top_n],
        "aggregated_opinions": aggregated_opinions,  # 原始融合数据
    }


# ============================================================================
# KANO 需求分层 (§4.5.3)
# ============================================================================

def classify_kano_model(
    entities_data: list[dict[str, Any]],
    opinions_data: dict[str, list[dict[str, Any]]],
    mentions_threshold: int = 3,
    heat_threshold_percentile: float = 0.7,
) -> dict[str, list[dict[str, Any]]]:
    """KANO 需求分层分类

    分类规则 (§4.5.3)：
    - **基本型 (Must-be)**：High Mentions (普遍) + Negative Sentiment (痛点)
      → 高频痛点，如 "发热"
    - **兴奋型 (Attractive)**：Low Mentions (稀缺) + High Avg_CII (高共鸣) + Positive Sentiment
      → 惊喜功能，如 "微距"
    - **期望型 (One-dimensional)**：High Mentions (普遍) + High Expectations
      → 用户愿望，如 "降价"

    Args:
        entities_data: 实体列表（仅 target 实体）
        opinions_data: 观点数据 {"top_issues": [...], "top_features": [...]}
        mentions_threshold: 高频门槛
        heat_threshold_percentile: 高热度百分位

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

    # 收集所有 issues 和 features
    all_issues = opinions_data.get("top_issues", [])
    all_features = opinions_data.get("top_features", [])

    # 从实体中提取 issues 和 features
    entity_issues: dict[str, dict] = {}
    entity_features: dict[str, dict] = {}

    for entity in entities_data:
        heat = entity.get("heat", 0)
        mentions = entity.get("mentions", 0)
        entity_post_ids = entity.get("post_ids", [])

        # 提取实体的 issues
        for issue in entity.get("top_issues", []):
            if issue not in entity_issues:
                entity_issues[issue] = {"label": issue, "heat": 0, "mentions": 0, "post_ids": set()}
            entity_issues[issue]["heat"] += heat
            entity_issues[issue]["mentions"] += mentions
            entity_issues[issue]["post_ids"].update(entity_post_ids)

        # 提取实体的 features
        for feature in entity.get("top_features", []):
            if feature not in entity_features:
                entity_features[feature] = {"label": feature, "heat": 0, "mentions": 0, "post_ids": set()}
            entity_features[feature]["heat"] += heat
            entity_features[feature]["mentions"] += mentions
            entity_features[feature]["post_ids"].update(entity_post_ids)

    # 计算热度阈值（用于判断"高热度"）
    all_heats = [i.get("heat", 0) for i in all_issues + all_features]
    all_heats.extend([v["heat"] for v in entity_issues.values()])
    all_heats.extend([v["heat"] for v in entity_features.values()])

    if all_heats:
        all_heats_sorted = sorted(all_heats)
        heat_threshold = all_heats_sorted[int(len(all_heats_sorted) * heat_threshold_percentile)]
    else:
        heat_threshold = 0

    # 分类逻辑
    # 1. Must-be (基本型)：高频 + 负面
    for item in all_issues:
        mentions = item.get("mentions", 0)
        if mentions >= mentions_threshold:
            must_be.append({
                "label": item.get("topic", ""),
                "heat": item.get("heat", 0),
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
                "top_opinions": item.get("top_opinions", []),
            })

    # 从实体 issues 中补充
    for label, data in entity_issues.items():
        if data["mentions"] >= mentions_threshold:
            # 检查是否已存在
            if not any(m["label"] == label for m in must_be):
                must_be.append({
                    "label": label,
                    "heat": data["heat"],
                    "mentions": data["mentions"],
                    "sentiment": -1,  # issues 默认负面
                    "post_ids": list(data.get("post_ids", set())),
                    "top_opinions": [],  # 实体级 issues 暂无具体观点
                })

    # 2. Attractive (兴奋型)：低频 + 高热度 + 正面
    for item in all_features:
        mentions = item.get("mentions", 0)
        heat = item.get("heat", 0)
        # 低频但高热度 = 惊喜点
        if mentions < mentions_threshold and heat >= heat_threshold:
            attractive.append({
                "label": item.get("topic", ""),
                "heat": heat,
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
                "top_opinions": item.get("top_opinions", []),
            })

    # 从实体 features 中补充
    for label, data in entity_features.items():
        if data["mentions"] < mentions_threshold and data["heat"] >= heat_threshold:
            if not any(a["label"] == label for a in attractive):
                attractive.append({
                    "label": label,
                    "heat": data["heat"],
                    "mentions": data["mentions"],
                    "sentiment": 1,  # features 默认正面
                    "post_ids": list(data.get("post_ids", set())),
                    "top_opinions": [],  # 实体级 features 暂无具体观点
                })

    # 3. One-dimensional (期望型)：高频 + 高期望（正面特性）
    for item in all_features:
        mentions = item.get("mentions", 0)
        if mentions >= mentions_threshold:
            one_dimensional.append({
                "label": item.get("topic", ""),
                "heat": item.get("heat", 0),
                "mentions": mentions,
                "sentiment": item.get("sentiment", 0),
                "post_ids": item.get("post_ids", []),
                "top_opinions": item.get("top_opinions", []),
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
# 场景与人群画像聚合 (§4.5.4) - 从 aggregated_entities 派生
# ============================================================================

def derive_context_analysis(
    aggregated_entities: dict[str, dict[str, Any]],
    min_mentions: int = 2,
    top_n: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """从 aggregated_entities 派生场景与人群画像

    采用"先融合，后派生"架构：
    - 输入: aggregate_entities() 返回的 aggregated_entities（已完成实体名称归一化）
    - 输出: 场景和人群画像的聚合结果

    优势：
    1. 数据一致性：复用实体归一化结果，避免重复处理
    2. 维度完整性：scenarios/audience 已关联到归一化实体
    3. 追溯能力：通过 post_ids 支持反向追溯

    Args:
        aggregated_entities: aggregate_entities 返回的 aggregated_entities 字段
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

    # 遍历所有已归一化的实体
    for canonical_name, entity in aggregated_entities.items():
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
    print(
        f"[场景人群派生] 从 {len(aggregated_entities)} 个实体派生: "
        f"场景 {len(scenarios)} 个, 人群 {len(audiences)} 个"
    )

    return {
        "scenarios": scenarios[:top_n],
        "audiences": audiences[:top_n],
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

    # 0. 获取任务信息（关键词用于主体过滤）
    task_stmt = select(DataTask).where(DataTask.id == task_id)
    task = db.execute(task_stmt).scalar_one_or_none()

    task_keywords: list[str] = []
    if task and task.keywords:
        # 关键词可能是逗号分隔的字符串
        task_keywords = [k.strip() for k in task.keywords.split(",") if k.strip()]
        logger.info(f"任务 {task_id} 关键词: {task_keywords}")

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

    # 3. 计算基础指标 (§4.1)
    nsr = calculate_nsr(posts_data)
    avg_cii = sum(p["cii"] for p in posts_data) / len(posts_data) if posts_data else 0
    serp_health = calculate_serp_health(posts_data_sorted)

    # 营销浓度
    marketing_stats = calculate_marketing_density(posts_data)

    # 舆论反差度
    sentiment_conflict = calculate_sentiment_conflict(posts_data)

    # 4. 时效性分布 (§4.2)
    time_distribution = calculate_time_distribution(posts_data)

    # 5. 实体聚合（主体过滤 §4.3）
    entity_stats = aggregate_entities(posts_data, task_keywords=task_keywords)

    # 6. 观点聚合
    opinion_stats = aggregate_opinions(posts_data)

    # 7. 四象限数据
    quadrant_data = generate_quadrant_data(posts_data)
    quadrant_summary = get_quadrant_summary(quadrant_data)

    # 8. KANO 需求分层 (§4.5.3)
    target_entities = entity_stats.get("target_entities", [])
    kano_model = classify_kano_model(target_entities, opinion_stats)

    # 9. 场景与人群画像 (§4.5.4) - 从 aggregated_entities 派生
    aggregated_entities = entity_stats.get("aggregated_entities", {})
    context_analysis = derive_context_analysis(aggregated_entities)

    # 10. 竞品分析
    competition = analyze_competition(entity_stats)

    # 11. KOL 声音提取
    kol_voices = extract_kol_voices(posts_data, db)

    # 12. 组装结果
    result_data = {
        "meta": {
            "task_id": task_id,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "keywords": task_keywords,  # 记录用于分析的关键词
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
            "marketing_analysis": marketing_stats,
            "sentiment_conflict": sentiment_conflict,
        },
        "charts": {
            "quadrant": quadrant_data[:50],
            "quadrant_summary": quadrant_summary,
            "time_distribution": time_distribution.get("distribution", []),
        },
        "freshness": time_distribution.get("freshness", {}),
        "insights": {
            # 实体分类（§4.3 主体过滤结果）
            "top_entities": entity_stats.get("top_entities", []),
            "target_entities": entity_stats.get("target_entities", []),
            "competitor_entities": entity_stats.get("competitor_entities", []),
            # 观点统计（带来源分布）
            "top_issues": opinion_stats.get("top_issues", []),
            "top_features": opinion_stats.get("top_features", []),
            # 场景与人群画像 (§4.5.4)
            "context_analysis": context_analysis,
            # KANO 需求分层 (§4.5.3)
            "opportunities": {
                "kano_model": kano_model,
            },
            # 竞品分析
            "competition": competition,
            # KOL 声音
            "kol_voices": kol_voices,
        },
        # 原始融合数据（用于项目级分析）
        "aggregated_entities": entity_stats.get("aggregated_entities", {}),
        "aggregated_opinions": opinion_stats.get("aggregated_opinions", {}),
    }

    # 统计实体分类数量
    target_count = len(entity_stats.get("target_entities", []))
    competitor_count = len(entity_stats.get("competitor_entities", []))

    logger.info(
        f"任务 {task_id} 聚合完成: "
        f"NSR={nsr:.3f}, AvgCII={avg_cii:.2f}, SERP={serp_health}, "
        f"营销占比={marketing_stats['promotion_ratio']:.1%}, "
        f"反差风险={sentiment_conflict['risk_level']}, "
        f"Target实体={target_count}, Competitor实体={competitor_count}"
    )

    return result_data


def _empty_result() -> dict[str, Any]:
    """返回空结果结构"""
    return {
        "meta": {
            "task_id": None,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "keywords": [],
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
            "marketing_analysis": {
                "promotion_ratio": 0.0,
                "organic_ratio": 1.0,
                "promotion_count": 0,
                "organic_count": 0,
            },
            "sentiment_conflict": {
                "avg_conflict": 0.0,
                "conflict_direction": "aligned",
                "high_conflict_count": 0,
                "risk_level": "low",
            },
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
            "time_distribution": [],
        },
        "freshness": {
            "last_7_days": 0.0,
            "last_30_days": 0.0,
            "avg_age_days": 0,
        },
        "insights": {
            "top_entities": [],
            "target_entities": [],
            "competitor_entities": [],
            "top_issues": [],
            "top_features": [],
            "context_analysis": {
                "scenarios": [],
                "audiences": [],
            },
            "opportunities": {
                "kano_model": {
                    "must_be": [],
                    "attractive": [],
                    "one_dimensional": [],
                },
            },
            "competition": {
                "top_competitors": [],
                "comparison_sentiment": 0.0,
                "target_sentiment": 0.0,
                "competitor_sentiment": 0.0,
                "competitor_details": [],
            },
            "kol_voices": [],
        },
        "aggregated_entities": {},
        "aggregated_opinions": {},
    }
