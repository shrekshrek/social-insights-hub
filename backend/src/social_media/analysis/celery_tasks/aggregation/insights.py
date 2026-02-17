"""派生洞察模块

从 aggregated_entities 和 aggregated_opinions 派生的高级洞察，包含：
1. 产品力诊断 (IPA Analysis) - 基于 opinions + target 实体的 features/issues
2. "人-货-场-竞" 关联网络 (Context Graph) - 增强版，包含竞品和产品属性节点
3. 精细化竞品雷达 (Competitor Radar) - 支持品牌聚合
4. KOL 声音提取 (KOL Voices)

设计原则：
- **小样本优先**: 适应 100 篇左右的小样本数据，引入动态阈值和降级策略。
- **定性优于定量**: 提供“发现线索”而非“统计推断”，利用 post_ids 进行集合运算。
- **纯计算逻辑**: 本模块为后处理步骤，不涉及 LLM 调用。

参考设计文档: docs/analysis_design/DERIVED_ANALYSIS_DESIGN.md
"""

import logging
import math
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_impact_score,
)
from src.social_media.tasks.models import SocialPost

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 产品力诊断 (IPA Analysis)
# ============================================================================


def _extract_entity_attributes_for_ipa(
    target_entity: Optional[dict[str, Any]],
    avg_heat_per_mention: float = 50.0,  # 由调用方传入 opinions 的平均值
) -> list[dict[str, Any]]:
    """从 Target 实体中提取 features/issues 作为 IPA 候选项

    将实体属性转换为统一格式：{name, mentions, sentiment, heat, post_ids, source_type}

    Args:
        target_entity: 目标实体数据
        avg_heat_per_mention: 平均每个 mention 的 heat 值（由 opinions 计算得出）
    """
    if not target_entity:
        return []

    candidates = []

    # 获取实体级别的 post_source_ids 和 comment_source_ids，用于拆分特征的 post_ids
    entity_post_sources = set(target_entity.get("post_source_ids", []))
    entity_comment_sources = set(target_entity.get("comment_source_ids", []))

    # 提取 features（正面属性，sentiment 设为正值）
    for feature in target_entity.get("features", []):
        if isinstance(feature, dict) and feature.get("text"):
            post_ids = feature.get("post_ids", [])
            mentions = len(post_ids)
            if mentions >= 1:
                # 使用实体级别的来源信息拆分 post_ids
                post_ids_set = set(post_ids)
                post_source_ids = list(post_ids_set & entity_post_sources)
                comment_source_ids = list(post_ids_set & entity_comment_sources)

                item = {
                    "name": feature["text"],
                    "mentions": mentions,
                    "sentiment": 0.5,  # features 默认正面
                    "heat": round(mentions * avg_heat_per_mention, 1),
                    "post_ids": post_ids,
                    "post_source_ids": post_source_ids,
                    "comment_source_ids": comment_source_ids,
                    "source_type": "feature",
                }
                # 透传原始词条（仅当该属性发生过合并时才会存在）
                original_terms = feature.get("original_terms")
                if (
                    original_terms
                    and isinstance(original_terms, list)
                    and len(original_terms) > 0
                ):
                    item["original_terms"] = original_terms
                candidates.append(item)

    # 提取 issues（负面属性，sentiment 设为负值）
    for issue in target_entity.get("issues", []):
        if isinstance(issue, dict) and issue.get("text"):
            post_ids = issue.get("post_ids", [])
            mentions = len(post_ids)
            if mentions >= 1:
                # 使用实体级别的来源信息拆分 post_ids
                post_ids_set = set(post_ids)
                post_source_ids = list(post_ids_set & entity_post_sources)
                comment_source_ids = list(post_ids_set & entity_comment_sources)

                item = {
                    "name": issue["text"],
                    "mentions": mentions,
                    "sentiment": -0.5,  # issues 默认负面
                    "heat": round(mentions * avg_heat_per_mention, 1),
                    "post_ids": post_ids,
                    "post_source_ids": post_source_ids,
                    "comment_source_ids": comment_source_ids,
                    "source_type": "issue",
                }
                # 透传原始词条（仅当该属性发生过合并时才会存在）
                original_terms = issue.get("original_terms")
                if (
                    original_terms
                    and isinstance(original_terms, list)
                    and len(original_terms) > 0
                ):
                    item["original_terms"] = original_terms
                candidates.append(item)

    return candidates


def perform_ipa_analysis(
    aggregated_opinions: list[dict[str, Any]],
    target_entity: Optional[dict[str, Any]] = None,
    min_mentions: int = 3,
) -> dict[str, Any]:
    """执行 IPA (Importance-Performance Analysis) 产品力诊断

    数据来源：
    1. aggregated_opinions - 通用观点（按 category 分组）
    2. target_entity.features/issues - Target 实体的产品属性（新增）

    坐标系：
    - X轴 (重要性): mentions (提及次数)
    - Y轴 (表现): sentiment (情感值 -1 ~ 1)
    - 气泡大小: heat (Total Impact)

    Args:
        aggregated_opinions: 聚合后的观点列表
        target_entity: Target 实体（可选，用于提取产品属性）
        min_mentions: 最小提及次数，过滤小样本噪点
    """
    quadrants = {
        "strength": [],  # Q1 优势区 (High Importance, High Performance)
        "improvement": [],  # Q2 改进区 (High Importance, Low Performance)
        "maintain": [],  # Q3 维持区 (Low Importance, Low Performance)
        "opportunity": [],  # Q4 机会区 (Low Importance, High Performance)
    }

    # IPA 数据来源：
    # 1. aggregated_opinions（通用观点）
    # 2. target_entity 的 features/issues（产品属性）
    candidates = list(aggregated_opinions)

    # 计算 opinions 的平均 heat per mention，用于估算 features/issues 的 heat
    # 这样 features/issues 和 opinions 的点位大小在同一数量级
    total_heat = sum(op.get("heat", 0) for op in aggregated_opinions)
    total_mentions = sum(op.get("mentions", 1) for op in aggregated_opinions)
    avg_heat_per_mention = (
        total_heat / max(total_mentions, 1) if aggregated_opinions else 50.0
    )

    # 增加 Target 实体的产品属性
    entity_attrs = _extract_entity_attributes_for_ipa(
        target_entity, avg_heat_per_mention
    )
    candidates.extend(entity_attrs)

    if not candidates:
        return {"quadrants": quadrants, "thresholds": {"x": 0, "y": 0}}

    # 2. 计算阈值 (动态计算中位数)
    # 使用 mentions 作为 X 轴依据 (更符合 IPA "Importance" 定义)
    all_mentions = [
        c.get("mentions", 0) for c in candidates if c.get("mentions", 0) >= min_mentions
    ]
    if not all_mentions:
        return {"quadrants": quadrants, "thresholds": {"x": 0, "y": 0}}

    # 简单的中位数计算
    all_mentions.sort()
    mid_idx = len(all_mentions) // 2
    avg_mentions = all_mentions[mid_idx]  # 使用中位数作为 X 轴分割线

    # Y轴分割线通常固定为 0 (中性)
    sentiment_threshold = 0.0

    # 收集所有有效点的 heat 值，用于归一化 z 值
    valid_heats = [
        c.get("heat", 0.0)
        for c in candidates
        if c.get("name") and c.get("mentions", 0) >= min_mentions
    ]
    heat_min = min(valid_heats) if valid_heats else 0
    heat_max = max(valid_heats) if valid_heats else 1
    heat_range = heat_max - heat_min if heat_max > heat_min else 1

    # Z 值映射参数：归一化到 [Z_MIN, Z_MAX] 范围
    # 前端会用 size = 4 + z * 3，限制在 [8, 40]
    # 所以 z 应该在 [1.5, 12] 左右，确保 size 在 [8.5, 40] 之间
    Z_MIN, Z_MAX = 2.0, 10.0

    # 3. 划分象限
    processed_names = set()  # 去重

    for item in candidates:
        name = item.get("name")
        if not name or name in processed_names:
            continue

        mentions = item.get("mentions", 0)
        if mentions < min_mentions:
            continue

        sentiment = item.get("sentiment", 0.0)
        heat = item.get("heat", 0.0)

        # 计算 Z 值 (Bubble Size)
        # 使用平方根归一化：先归一化到 [0,1]，再用 sqrt 使中小值差异更明显，最后映射到 [Z_MIN, Z_MAX]
        normalized = (heat - heat_min) / heat_range
        z_val = Z_MIN + (Z_MAX - Z_MIN) * math.sqrt(normalized)

        point = {
            "name": name,
            "x": mentions,  # Importance (Mentions)
            "y": round(sentiment, 2),  # Performance
            "z": round(z_val, 2),  # Bubble Size (Normalized)
            "heat": round(heat, 2),
            "post_ids": list(item.get("post_ids", [])),  # 支持溯源
            "post_source_ids": list(item.get("post_source_ids", [])),
            "comment_source_ids": list(item.get("comment_source_ids", [])),
        }

        # 如果是观点集合，添加原始观点列表
        original_terms = item.get("original_terms")
        if (
            original_terms
            and isinstance(original_terms, list)
            and len(original_terms) > 0
        ):
            point["original_terms"] = original_terms

        # 透传 spam_distribution（用于前端维度筛选）
        spam_dist = item.get("spam_distribution")
        if spam_dist:
            point["spam_distribution"] = spam_dist

        # 判定逻辑
        is_high_importance = mentions >= avg_mentions
        is_high_performance = sentiment >= sentiment_threshold

        if is_high_importance and is_high_performance:
            quadrants["strength"].append(point)
        elif is_high_importance and not is_high_performance:
            quadrants["improvement"].append(point)
        elif not is_high_importance and not is_high_performance:
            quadrants["maintain"].append(point)
        else:  # Low Importance, High Performance
            quadrants["opportunity"].append(point)

        processed_names.add(name)

    # 4. 排序并限制返回数量 (防止图表拥挤)
    # 策略：对相同坐标(x,y)的点，只保留前 N 个（按 heat 排序）
    MAX_POINTS_PER_COORD = 10

    final_quadrants = {
        "strength": [],
        "improvement": [],
        "maintain": [],
        "opportunity": [],
    }

    # 合并所有点进行总排序
    all_points = []
    for q_name, points in quadrants.items():
        for p in points:
            p["quadrant_label"] = q_name  # 标记原始象限
            all_points.append(p)

    # 按 heat 降序排序
    all_points.sort(key=lambda x: x["heat"], reverse=True)

    # 对相同坐标的点进行限制：每个 (x, y) 坐标最多保留 MAX_POINTS_PER_COORD 个
    coord_counts: dict[tuple, int] = {}  # (x, y) -> count
    filtered_points = []

    for p in all_points:
        coord = (p["x"], p["y"])
        count = coord_counts.get(coord, 0)
        if count < MAX_POINTS_PER_COORD:
            filtered_points.append(p)
            coord_counts[coord] = count + 1

    # 重新分配回象限
    for p in filtered_points:
        q_label = p.pop("quadrant_label")
        final_quadrants[q_label].append(p)

    return {
        "quadrants": final_quadrants,
        "thresholds": {"x": avg_mentions, "y": sentiment_threshold},
    }


# ============================================================================
# 2. "人-货-场-竞" 关联网络 (Context Graph)
# ============================================================================


def build_context_graph(
    target_entity: Optional[dict[str, Any]],
    aggregated_opinions: list[dict[str, Any]],
    competitor_entities: Optional[list[dict[str, Any]]] = None,
    top_n_per_type: int = 3,
    spam_map: Optional[dict[int, str]] = None,
) -> dict[str, Any]:
    """构建以 Target 实体为中心的星形关联网络

    节点类型：
    - audience: 人群（来自 target_entity.audience）
    - scenario: 场景（来自 target_entity.scenarios）
    - feature: 产品优点（来自 target_entity.features）
    - issue: 产品问题（来自 target_entity.issues）
    - topic: 话题（来自 aggregated_opinions）
    - competitor: 竞品（来自 competitor_entities）

    基于 post_ids 的 Jaccard 相似度计算共现关系。

    Args:
        target_entity: Target 实体
        aggregated_opinions: 聚合后的观点
        competitor_entities: 竞品实体列表
        top_n_per_type: 每种类型最多保留的节点数
        spam_map: post_id -> spam 分组映射 (可选)。若提供，返回按维度拆分的 3 版本

    Returns:
        若 spam_map 为 None: { "center_node": str, "nodes": list, "edges": list }
        若 spam_map 非 None: { "all": {...}, "organic": {...}, "promo": {...} }
    """
    if not target_entity:
        # 无 target 实体时返回 3 层空图
        empty_graph = {"center_node": None, "nodes": [], "edges": []}
        return {"all": empty_graph, "organic": empty_graph, "promo": empty_graph}

    center_name = target_entity["name"]
    center_pids = set(target_entity.get("post_ids", []))

    if not center_pids:
        # 提前返回空图（总是三层结构）
        empty_graph = {"center_node": center_name, "nodes": [], "edges": []}
        return {"all": empty_graph, "organic": empty_graph, "promo": empty_graph}

    # 辅助函数：按 spam 维度过滤 post_ids
    def _filter_pids_by_dimension(pids: set[int], dimension: str) -> set[int]:
        """按维度过滤 post_ids"""
        if dimension == "all" or spam_map is None:
            return pids
        if dimension == "organic":
            return {pid for pid in pids if spam_map.get(pid) == "low"}
        if dimension == "promo":
            return {pid for pid in pids if spam_map.get(pid) == "high"}
        return pids

    # 辅助函数：构建单个维度的图
    def _build_single_graph(
        dimension_center_pids: set[int], dimension: str
    ) -> dict[str, Any]:
        """为指定维度构建关联网络"""
        if not dimension_center_pids:
            return {"center_node": center_name, "nodes": [], "edges": []}

        # 按类型分组的候选节点池（维度过滤后）
        candidates_by_type: dict[str, list[dict]] = {
            "audience": [],
            "scenario": [],
            "feature": [],
            "issue": [],
            "topic": [],
            "competitor": [],
        }

        # 1. 提取人群 (来自 Target 实体的属性)
        for aud_item in target_entity.get("audience", []):
            if isinstance(aud_item, dict) and aud_item.get("text"):
                filtered_pids = _filter_pids_by_dimension(
                    set(aud_item.get("post_ids", [])), dimension
                )
                if filtered_pids:
                    candidates_by_type["audience"].append(
                        {
                            "name": aud_item["text"],
                            "type": "audience",
                            "post_ids": filtered_pids,
                        }
                    )

        # 2. 提取场景
        for scn_item in target_entity.get("scenarios", []):
            if isinstance(scn_item, dict) and scn_item.get("text"):
                filtered_pids = _filter_pids_by_dimension(
                    set(scn_item.get("post_ids", [])), dimension
                )
                if filtered_pids:
                    candidates_by_type["scenario"].append(
                        {
                            "name": scn_item["text"],
                            "type": "scenario",
                            "post_ids": filtered_pids,
                        }
                    )

        # 3. 提取产品优点 (features)
        for feat_item in target_entity.get("features", []):
            if isinstance(feat_item, dict) and feat_item.get("text"):
                filtered_pids = _filter_pids_by_dimension(
                    set(feat_item.get("post_ids", [])), dimension
                )
                if filtered_pids:
                    candidates_by_type["feature"].append(
                        {
                            "name": feat_item["text"],
                            "type": "feature",
                            "sentiment": 0.5,
                            "post_ids": filtered_pids,
                        }
                    )

        # 4. 提取产品问题 (issues)
        for issue_item in target_entity.get("issues", []):
            if isinstance(issue_item, dict) and issue_item.get("text"):
                filtered_pids = _filter_pids_by_dimension(
                    set(issue_item.get("post_ids", [])), dimension
                )
                if filtered_pids:
                    candidates_by_type["issue"].append(
                        {
                            "name": issue_item["text"],
                            "type": "issue",
                            "sentiment": -0.5,
                            "post_ids": filtered_pids,
                        }
                    )

        # 5. 提取主要话题 (来自 Top Opinions)
        for topic in aggregated_opinions[:10]:
            filtered_pids = _filter_pids_by_dimension(
                set(topic.get("post_ids", [])), dimension
            )
            if filtered_pids:
                candidates_by_type["topic"].append(
                    {
                        "name": topic["name"],
                        "type": "topic",
                        "sentiment": topic.get("sentiment", 0),
                        "post_ids": filtered_pids,
                    }
                )

        # 6. 提取竞品 (来自 competitor_entities)
        if competitor_entities:
            for comp in competitor_entities:
                if comp.get("name") and comp.get("name") != center_name:
                    filtered_pids = _filter_pids_by_dimension(
                        set(comp.get("post_ids", [])), dimension
                    )
                    if filtered_pids:
                        candidates_by_type["competitor"].append(
                            {
                                "name": comp["name"],
                                "type": "competitor",
                                "sentiment": comp.get("sentiment", 0),
                                "post_ids": filtered_pids,
                            }
                        )

        # 计算 Jaccard 相似度并按类型分组排序
        def _calc_jaccard_nodes(candidates: list[dict]) -> list[dict]:
            """计算候选节点的 Jaccard 相似度"""
            result = []
            for cand in candidates:
                cand_pids = cand["post_ids"]
                if not cand_pids:
                    continue

                intersection = dimension_center_pids.intersection(cand_pids)
                union = dimension_center_pids.union(cand_pids)

                co_occurrence = len(intersection)
                if co_occurrence < 1:
                    continue

                jaccard = co_occurrence / len(union)

                result.append(
                    {
                        "name": cand["name"],
                        "type": cand["type"],
                        "weight": jaccard,
                        "co_occurrence": co_occurrence,
                        "sentiment": cand.get("sentiment"),
                        "post_ids": list(intersection),
                    }
                )

            # 按权重降序排序
            result.sort(key=lambda x: x["weight"], reverse=True)
            return result

        # 每种类型取 Top N
        nodes = []
        edges = []

        for node_type, candidates in candidates_by_type.items():
            ranked = _calc_jaccard_nodes(candidates)
            for node in ranked[:top_n_per_type]:
                nodes.append(node)
                edges.append(
                    {
                        "source": center_name,
                        "target": node["name"],
                        "value": round(node["weight"], 3),
                    }
                )

        return {"center_node": center_name, "nodes": nodes, "edges": edges}

    # 总是返回三层结构
    # 如果没有 spam_map 或为空，所有维度返回相同数据（全量）
    if spam_map is None or not spam_map:
        all_graph = _build_single_graph(center_pids, "all")
        return {
            "all": all_graph,
            "organic": all_graph,
            "promo": all_graph,
        }

    # 有 spam_map，计算 3 个不同版本
    return {
        "all": _build_single_graph(center_pids, "all"),
        "organic": _build_single_graph(
            _filter_pids_by_dimension(center_pids, "organic"), "organic"
        ),
        "promo": _build_single_graph(
            _filter_pids_by_dimension(center_pids, "promo"), "promo"
        ),
    }



# ============================================================================
# 3. 精细化竞品雷达 (Competitor Radar)
# ============================================================================


def _get_entity_parent(entity: dict) -> str:
    """获取实体的 parent（品牌归属）

    优先使用 tags.parent，否则使用实体名称本身
    """
    tags = entity.get("tags", {})
    parent = tags.get("parent", "")
    # "Self" 表示自身就是品牌，用实体名称
    if not parent or parent.lower() == "self":
        return entity.get("name", "Unknown")
    return parent


def _aggregate_entities_by_parent(
    entities: list[dict[str, Any]], role_filter: str | None = None
) -> dict[str, dict[str, Any]]:
    """按 parent（品牌）聚合实体

    Args:
        entities: 实体列表
        role_filter: 可选的角色过滤（如 "target", "competitor"）

    Returns:
        {parent_name: aggregated_stats}
    """
    brand_stats: dict[str, dict] = {}

    for entity in entities:
        # 角色过滤
        if role_filter:
            entity_role = entity.get("role", "").lower()
            tags_role = entity.get("tags", {}).get("role", "").lower()
            if entity_role != role_filter and tags_role != role_filter:
                continue

        parent = _get_entity_parent(entity)

        if parent not in brand_stats:
            brand_stats[parent] = {
                "name": parent,
                "mentions": 0,
                "heat": 0.0,
                "sentiment_weighted_sum": 0.0,
                "sentiment_weight": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "product_count": 0,
                "products": [],  # 记录包含的产品
                "post_ids": set(),
                "post_source_ids": set(),
                "comment_source_ids": set(),
            }

        stats = brand_stats[parent]
        stats["mentions"] += entity.get("mentions", 0)
        stats["heat"] += entity.get("heat", 0)
        stats["product_count"] += 1
        stats["products"].append(entity.get("name", ""))
        stats["post_ids"].update(entity.get("post_ids", []))
        stats["post_source_ids"].update(entity.get("post_source_ids", []))
        stats["comment_source_ids"].update(entity.get("comment_source_ids", []))

        # 加权情感（按 mentions 加权）
        entity_mentions = entity.get("mentions", 1)
        stats["sentiment_weighted_sum"] += entity.get("sentiment", 0) * entity_mentions
        stats["sentiment_weight"] += entity_mentions

        # 情感分布累加
        dist = entity.get("sentiment_distribution", {})
        stats["positive_count"] += dist.get("positive", 0)
        stats["negative_count"] += dist.get("negative", 0)
        stats["neutral_count"] += dist.get("neutral", 0)

    # 计算聚合后的情感和分布
    for parent, stats in brand_stats.items():
        if stats["sentiment_weight"] > 0:
            stats["sentiment"] = round(
                stats["sentiment_weighted_sum"] / stats["sentiment_weight"], 2
            )
        else:
            stats["sentiment"] = 0.0

        stats["sentiment_distribution"] = {
            "positive": stats["positive_count"],
            "negative": stats["negative_count"],
            "neutral": stats["neutral_count"],
        }

        # 清理临时字段
        del stats["sentiment_weighted_sum"]
        del stats["sentiment_weight"]
        del stats["positive_count"]
        del stats["negative_count"]
        del stats["neutral_count"]

        stats["post_ids"] = list(stats["post_ids"])
        stats["post_source_ids"] = list(stats["post_source_ids"])
        stats["comment_source_ids"] = list(stats["comment_source_ids"])

    return brand_stats


def analyze_competitor_radar(
    target_entity: Optional[dict[str, Any]],
    competitor_entities: list[dict[str, Any]],
    aggregated_entities: list[dict[str, Any]],
    max_competitors: int = 4,  # 最多显示的竞品数量（加上本品最多5条线）
    spam_map: Optional[dict[int, str]] = None,
    posts_data: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """竞品雷达分析 (带品牌聚合，支持多品牌对比)

    改进：
    1. 使用 tags.parent 将同品牌产品聚合后对比品牌整体表现
    2. 支持多个竞品品牌（数据充足时）
    3. 若提供 spam_map 和 posts_data，返回按维度拆分的 3 版本

    Args:
        target_entity: 目标实体
        competitor_entities: 竞品实体列表
        aggregated_entities: 聚合后的所有实体
        max_competitors: 最多显示的竞品数量
        spam_map: post_id -> spam 分组映射 (可选)
        posts_data: 原始帖子数据列表 (可选)

    Returns:
        若 spam_map 为 None: { "mode": str, "series": list, ... }
        若 spam_map 非 None: { "all": {...}, "organic": {...}, "promo": {...} }
    """
    if not target_entity or not competitor_entities:
        # 总是返回三层结构
        empty_result = {"mode": "none"}
        return {"all": empty_result, "organic": empty_result, "promo": empty_result}

    # 辅助函数：按 spam 维度过滤 post_ids
    def _match_dimension(pid: int, dimension: str) -> bool:
        """判断 post_id 是否匹配指定维度"""
        if dimension == "all" or spam_map is None:
            return True
        if dimension == "organic":
            return spam_map.get(pid) == "low"
        if dimension == "promo":
            return spam_map.get(pid) == "high"
        return False

    # 辅助函数：按维度重新聚合实体统计
    def _aggregate_entity_stats_by_dimension(
        entity: dict, dimension: str
    ) -> dict:
        """按 spam 维度重新聚合实体的统计字段"""
        if spam_map is None or posts_data is None or dimension == "all":
            # 无 spam_map 或 all 维度，返回原始统计
            return entity

        # 1. 过滤 post_source_ids 和 comment_source_ids
        post_src = [
            pid
            for pid in entity.get("post_source_ids", [])
            if _match_dimension(pid, dimension)
        ]
        comment_src = [
            pid
            for pid in entity.get("comment_source_ids", [])
            if _match_dimension(pid, dimension)
        ]

        # 2. 从 posts_data 中提取对应帖子的统计数据
        mentions = len(post_src) + len(comment_src)

        # 3. 计算 heat (从 posts_data 中取 cii 求和)
        heat = 0.0
        for post in posts_data:
            pid = post.get("post_id")
            if pid in post_src or pid in comment_src:
                heat += post.get("cii", 0)

        # 4. 计算加权 sentiment 和 sentiment_distribution
        sentiment_weighted_sum = 0.0
        sentiment_weight = 0
        pos_count = neg_count = neu_count = 0
        for post in posts_data:
            pid = post.get("post_id")
            if pid in post_src or pid in comment_src:
                post_sentiment = post.get("sentiment", 0)
                post_cii = post.get("cii", 1)
                sentiment_weighted_sum += post_sentiment * post_cii
                sentiment_weight += post_cii
                if post_sentiment > 0:
                    pos_count += 1
                elif post_sentiment < 0:
                    neg_count += 1
                else:
                    neu_count += 1

        sentiment = (
            sentiment_weighted_sum / sentiment_weight if sentiment_weight > 0 else 0
        )

        return {
            **entity,  # 保留其他字段
            "mentions": mentions,
            "heat": heat,
            "sentiment": sentiment,
            "sentiment_distribution": {
                "positive": pos_count,
                "negative": neg_count,
                "neutral": neu_count,
            },
            "post_source_ids": post_src,
            "comment_source_ids": comment_src,
        }

    # 内部函数：构建单个维度的雷达图
    def _build_single_radar(dimension: str) -> dict[str, Any]:
        """为指定维度构建竞品雷达图"""
        # 按维度重新聚合实体统计
        dim_target_data = _aggregate_entity_stats_by_dimension(target_entity, dimension)
        dim_aggregated_entities = [
            _aggregate_entity_stats_by_dimension(e, dimension)
            for e in aggregated_entities
        ]

        # 1. 按 parent 聚合实体（使用维度过滤后的数据）
        target_brands = _aggregate_entities_by_parent(
            dim_aggregated_entities, role_filter="target"
        )
        competitor_brands = _aggregate_entities_by_parent(
            dim_aggregated_entities, role_filter="competitor"
        )

        # 2. 准备 Target 数据
        target_parent = _get_entity_parent(dim_target_data)
        if (
            target_parent in target_brands
            and target_brands[target_parent]["product_count"] > 1
        ):
            target_data_single = target_brands[target_parent]
            target_name = f"{target_parent} ({target_data_single['product_count']}个产品)"
        else:
            target_data_single = dim_target_data
            target_name = dim_target_data["name"]

        # 3. 准备所有竞品数据（使用维度过滤后的 competitor_entities）
        competitor_data_list = []
        seen_parents = set()

        for comp in competitor_entities:
            # 从 dim_aggregated_entities 中找到对应的实体
            comp_name = comp.get("name")
            dim_comp = next(
                (e for e in dim_aggregated_entities if e.get("name") == comp_name), comp
            )

            comp_parent = _get_entity_parent(dim_comp)
            if comp_parent in seen_parents:
                continue
            seen_parents.add(comp_parent)

            if (
                comp_parent in competitor_brands
                and competitor_brands[comp_parent]["product_count"] > 1
            ):
                brand_data = competitor_brands[comp_parent]
                competitor_data_list.append(
                    {
                        "data": brand_data,
                        "name": f"{comp_parent} ({brand_data['product_count']}个产品)",
                        "products": brand_data.get("products", []),
                        "mentions": brand_data.get("mentions", 0),
                    }
                )
            else:
                competitor_data_list.append(
                    {
                        "data": dim_comp,
                        "name": dim_comp["name"],
                        "products": [dim_comp["name"]],
                        "mentions": dim_comp.get("mentions", 0),
                    }
                )

        # 按 mentions 排序并限制数量
        competitor_data_list.sort(key=lambda x: x["mentions"], reverse=True)
        competitor_data_list = competitor_data_list[:max_competitors]

        # 4. 检查是否有足够数据做雷达图
        has_enough_data = any(c["mentions"] >= 5 for c in competitor_data_list)

        if not has_enough_data:
            # Mode B: Bar Chart
            series = [
                {
                    "name": target_name,
                    "sentiment": target_data_single.get("sentiment", 0),
                    "sentiment_distribution": target_data_single.get("sentiment_distribution", {}),
                    "products": target_data_single.get("products", [dim_target_data["name"]]),
                    "post_ids": target_data_single.get("post_ids", []),
                    "post_source_ids": target_data_single.get("post_source_ids", []),
                    "comment_source_ids": target_data_single.get("comment_source_ids", []),
                }
            ]
            for comp in competitor_data_list:
                series.append(
                    {
                        "name": comp["name"],
                        "sentiment": comp["data"].get("sentiment", 0),
                        "sentiment_distribution": comp["data"].get("sentiment_distribution", {}),
                        "products": comp["products"],
                        "post_ids": comp["data"].get("post_ids", []),
                        "post_source_ids": comp["data"].get("post_source_ids", []),
                        "comment_source_ids": comp["data"].get("comment_source_ids", []),
                    }
                )
            return {"mode": "bar", "series": series}

        # Mode A: Radar
        def _get_radar_score(
            entity: dict, max_mentions: int, max_heat: float
        ) -> list[float]:
            m_score = min(entity.get("mentions", 0) / (max_mentions + 1), 1.0)
            s_score = (entity.get("sentiment", 0) + 1) / 2
            h_score = min(
                math.log(entity.get("heat", 0) + 1) / (math.log(max_heat + 1) + 0.1), 1.0
            )
            dist = entity.get("sentiment_distribution", {})
            total = sum(dist.values()) if dist else 1
            pos_score = dist.get("positive", 0) / total if total > 0 else 0
            neg_ratio = dist.get("negative", 0) / total if total > 0 else 0
            neg_control_score = 1.0 - neg_ratio
            return [
                round(m_score, 2),
                round(s_score, 2),
                round(h_score, 2),
                round(pos_score, 2),
                round(neg_control_score, 2),
            ]

        # 计算所有品牌的最大值用于归一化
        all_data = [target_data_single] + [c["data"] for c in competitor_data_list]
        max_mentions = max(d.get("mentions", 0) for d in all_data)
        max_heat = max(d.get("heat", 0) for d in all_data)

        # 构建 series
        series = [
            {
                "name": target_name,
                "data": _get_radar_score(target_data_single, max_mentions, max_heat),
                "products": target_data_single.get("products", [dim_target_data["name"]]),
                "post_ids": target_data_single.get("post_ids", []),
                "post_source_ids": target_data_single.get("post_source_ids", []),
                "comment_source_ids": target_data_single.get("comment_source_ids", []),
            }
        ]

        for comp in competitor_data_list:
            series.append(
                {
                    "name": comp["name"],
                    "data": _get_radar_score(comp["data"], max_mentions, max_heat),
                    "products": comp["products"],
                    "post_ids": comp["data"].get("post_ids", []),
                    "post_source_ids": comp["data"].get("post_source_ids", []),
                    "comment_source_ids": comp["data"].get("comment_source_ids", []),
                }
            )

        return {
            "mode": "radar",
            "dimensions": ["声量影响", "综合情感", "互动热度", "好评率", "差评控制"],
            "series": series,
        }

    # 总是返回三层结构
    # 如果没有 spam_map 或为空，所有维度返回相同数据（全量）
    if spam_map is None or not spam_map:
        all_radar = _build_single_radar("all")
        return {
            "all": all_radar,
            "organic": all_radar,
            "promo": all_radar,
        }

    # 有 spam_map，计算 3 个不同版本
    return {
        "all": _build_single_radar("all"),
        "organic": _build_single_radar("organic"),
        "promo": _build_single_radar("promo"),
    }


# 以下是原有代码，现已被提取到 _build_single_radar 中，需要删除
# 保留标记以便后续清理


# ============================================================================
# 4. KOL 声音提取
# ============================================================================


def extract_kol_voices(
    posts_data: list[dict[str, Any]], db: Session, top_n: int = 5
) -> list[dict[str, Any]]:
    """提取 KOL (关键意见领袖) 的声音

    使用 Impact Score (互动 x 质量) 进行排序，避免标题党霸榜
    """

    def get_impact(p):
        cii = p.get("cii", 0)
        value_score = p.get("value_score")
        return calculate_impact_score(cii, value_score)

    # 按 Impact Score 排序
    sorted_posts = sorted(posts_data, key=get_impact, reverse=True)
    top_posts = sorted_posts[:top_n]

    results = []
    for post_info in top_posts:
        post_id = post_info.get("post_id")
        if not post_id:
            continue

        stmt = select(SocialPost).where(SocialPost.id == post_id)
        post = db.execute(stmt).scalar_one_or_none()

        if post:
            deep_res = post_info.get("post_deep_result") or {}
            summary = deep_res.get("summary", "")

            results.append(
                {
                    "post_id": post.id,
                    "author": post.author_name or "未知作者",
                    "title": post.title
                    or (post.content[:20] + "..." if post.content else ""),
                    "cii": post_info.get("cii", 0),
                    "sentiment": post_info.get("sentiment", 0),
                    "summary": summary,
                    "platform": post.platform.value
                    if hasattr(post.platform, "value")
                    else str(post.platform),
                }
            )

    return results
