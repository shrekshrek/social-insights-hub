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
from typing import Any, List, Dict, Set, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.social_media.tasks.models import SocialPost

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 产品力诊断 (IPA Analysis)
# ============================================================================

def _extract_entity_attributes_for_ipa(
    target_entity: Optional[dict[str, Any]]
) -> list[dict[str, Any]]:
    """从 Target 实体中提取 features/issues 作为 IPA 候选项
    
    将实体属性转换为统一格式：{name, mentions, sentiment, heat, post_ids, source_type}
    """
    if not target_entity:
        return []
    
    candidates = []
    
    # 提取 features（正面属性，sentiment 设为正值）
    for feature in target_entity.get("features", []):
        if isinstance(feature, dict) and feature.get("text"):
            post_ids = feature.get("post_ids", [])
            mentions = len(post_ids)
            if mentions >= 1:
                candidates.append({
                    "name": feature["text"],
                    "mentions": mentions,
                    "sentiment": 0.5,  # features 默认正面
                    "heat": mentions * 1.0,  # 简化：用 mentions 近似 heat
                    "post_ids": post_ids,
                    "source_type": "feature"
                })
    
    # 提取 issues（负面属性，sentiment 设为负值）
    for issue in target_entity.get("issues", []):
        if isinstance(issue, dict) and issue.get("text"):
            post_ids = issue.get("post_ids", [])
            mentions = len(post_ids)
            if mentions >= 1:
                candidates.append({
                    "name": issue["text"],
                    "mentions": mentions,
                    "sentiment": -0.5,  # issues 默认负面
                    "heat": mentions * 1.0,
                    "post_ids": post_ids,
                    "source_type": "issue"
                })
    
    return candidates


def perform_ipa_analysis(
    aggregated_opinions: list[dict[str, Any]],
    target_entity: Optional[dict[str, Any]] = None,
    min_mentions: int = 3
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
        "strength": [],     # Q1 优势区 (High Importance, High Performance)
        "improvement": [],  # Q2 改进区 (High Importance, Low Performance)
        "maintain": [],     # Q3 维持区 (Low Importance, Low Performance)
        "opportunity": []   # Q4 机会区 (Low Importance, High Performance)
    }
    
    # IPA 数据来源：
    # 1. aggregated_opinions（通用观点）
    # 2. target_entity 的 features/issues（产品属性）
    candidates = list(aggregated_opinions)
    
    # 增加 Target 实体的产品属性
    entity_attrs = _extract_entity_attributes_for_ipa(target_entity)
    candidates.extend(entity_attrs)
    
    if not candidates:
        return {"quadrants": quadrants, "thresholds": {"x": 0, "y": 0}}
        
    # 2. 计算阈值 (动态计算中位数)
    # 使用 mentions 作为 X 轴依据 (更符合 IPA "Importance" 定义)
    all_mentions = [c.get("mentions", 0) for c in candidates if c.get("mentions", 0) >= min_mentions]
    if not all_mentions:
        return {"quadrants": quadrants, "thresholds": {"x": 0, "y": 0}}
        
    # 简单的中位数计算
    all_mentions.sort()
    mid_idx = len(all_mentions) // 2
    avg_mentions = all_mentions[mid_idx] # 使用中位数作为 X 轴分割线
    
    # Y轴分割线通常固定为 0 (中性)
    sentiment_threshold = 0.0
    
    # 3. 划分象限
    processed_names = set() # 去重
    
    for item in candidates:
        name = item.get("name")
        if not name or name in processed_names:
            continue
            
        mentions = item.get("mentions", 0)
        if mentions < min_mentions:
            continue
            
        sentiment = item.get("sentiment", 0.0)
        heat = item.get("heat", 0.0)
        
        # 计算适合前端展示的 Z 值 (Bubble Size)
        # 使用对数平滑：log(heat + 1)
        z_val = math.log(max(0, heat) + 1)
        
        point = {
            "name": name,
            "x": mentions, # Importance (Mentions)
            "y": round(sentiment, 2), # Performance
            "z": round(z_val, 2), # Bubble Size (Log Smoothed Impact)
            "heat": round(heat, 2),
            "post_ids": list(item.get("post_ids", [])) # 支持溯源
        }
        
        # 判定逻辑
        is_high_importance = mentions >= avg_mentions
        is_high_performance = sentiment >= sentiment_threshold
        
        if is_high_importance and is_high_performance:
            quadrants["strength"].append(point)
        elif is_high_importance and not is_high_performance:
            quadrants["improvement"].append(point)
        elif not is_high_importance and not is_high_performance:
            quadrants["maintain"].append(point)
        else: # Low Importance, High Performance
            quadrants["opportunity"].append(point)
            
        processed_names.add(name)
        
    # 4. 排序并限制返回数量 (防止图表拥挤)
    # 策略：保留所有点，不限制数量，但会进行排序
    
    final_quadrants = {
        "strength": [],
        "improvement": [],
        "maintain": [],
        "opportunity": []
    }
    
    # 合并所有点进行总排序，或者按象限配额
    # 这里采用总排序策略：按 heat (综合热度)
    all_points = []
    for q_name, points in quadrants.items():
        for p in points:
            p["quadrant_label"] = q_name # 标记原始象限
            all_points.append(p)
            
    # 按 heat 降序排序
    all_points.sort(key=lambda x: x["heat"], reverse=True)
    
    
    # 重新分配回象限
    for p in all_points:
        q_label = p.pop("quadrant_label")
        final_quadrants[q_label].append(p)

    return {
        "quadrants": final_quadrants,
        "thresholds": {
            "x": avg_mentions,
            "y": sentiment_threshold
        }
    }


# ============================================================================
# 2. "人-货-场-竞" 关联网络 (Context Graph)
# ============================================================================

def build_context_graph(
    target_entity: Optional[dict[str, Any]],
    aggregated_opinions: list[dict[str, Any]],
    competitor_entities: Optional[list[dict[str, Any]]] = None,
    top_n_per_type: int = 3
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
    """
    if not target_entity:
        return {}
        
    center_name = target_entity["name"]
    center_pids = set(target_entity.get("post_ids", []))
    
    if not center_pids:
        return {"center_node": center_name, "nodes": [], "edges": []}

    # 按类型分组的候选节点池
    candidates_by_type: dict[str, list[dict]] = {
        "audience": [],
        "scenario": [],
        "feature": [],
        "issue": [],
        "topic": [],
        "competitor": []
    }
    
    # 1. 提取人群 (来自 Target 实体的属性)
    for aud_item in target_entity.get("audience", []):
        if isinstance(aud_item, dict) and aud_item.get("text"):
            candidates_by_type["audience"].append({
                "name": aud_item["text"],
                "type": "audience",
                "post_ids": set(aud_item.get("post_ids", []))
            })
    
    # 2. 提取场景
    for scn_item in target_entity.get("scenarios", []):
        if isinstance(scn_item, dict) and scn_item.get("text"):
            candidates_by_type["scenario"].append({
                "name": scn_item["text"],
                "type": "scenario",
                "post_ids": set(scn_item.get("post_ids", []))
            })
    
    # 3. 提取产品优点 (features)
    for feat_item in target_entity.get("features", []):
        if isinstance(feat_item, dict) and feat_item.get("text"):
            candidates_by_type["feature"].append({
                "name": feat_item["text"],
                "type": "feature",
                "sentiment": 0.5,  # features 默认正面
                "post_ids": set(feat_item.get("post_ids", []))
            })
    
    # 4. 提取产品问题 (issues)
    for issue_item in target_entity.get("issues", []):
        if isinstance(issue_item, dict) and issue_item.get("text"):
            candidates_by_type["issue"].append({
                "name": issue_item["text"],
                "type": "issue",
                "sentiment": -0.5,  # issues 默认负面
                "post_ids": set(issue_item.get("post_ids", []))
            })
            
    # 5. 提取主要话题 (来自 Top Opinions)
    for topic in aggregated_opinions[:10]:
        candidates_by_type["topic"].append({
            "name": topic["name"],
            "type": "topic",
            "sentiment": topic.get("sentiment", 0),
            "post_ids": set(topic.get("post_ids", []))
        })
    
    # 6. 提取竞品 (来自 competitor_entities)
    if competitor_entities:
        for comp in competitor_entities:
            if comp.get("name") and comp.get("name") != center_name:
                candidates_by_type["competitor"].append({
                    "name": comp["name"],
                    "type": "competitor",
                    "sentiment": comp.get("sentiment", 0),
                    "post_ids": set(comp.get("post_ids", []))
                })
    
    # 计算 Jaccard 相似度并按类型分组排序
    def _calc_jaccard_nodes(candidates: list[dict]) -> list[dict]:
        """计算候选节点的 Jaccard 相似度"""
        result = []
        for cand in candidates:
            cand_pids = cand["post_ids"]
            if not cand_pids:
                continue
            
            intersection = center_pids.intersection(cand_pids)
            union = center_pids.union(cand_pids)
            
            co_occurrence = len(intersection)
            if co_occurrence < 1:
                continue
            
            jaccard = co_occurrence / len(union)
            
            result.append({
                "name": cand["name"],
                "type": cand["type"],
                "weight": jaccard,
                "co_occurrence": co_occurrence,
                "sentiment": cand.get("sentiment"),
                "post_ids": list(intersection)
            })
        
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
            edges.append({
                "source": center_name,
                "target": node["name"],
                "value": round(node["weight"], 3)
            })
        
    return {
        "center_node": center_name,
        "nodes": nodes,
        "edges": edges
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
    entities: list[dict[str, Any]],
    role_filter: str | None = None
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
            }
        
        stats = brand_stats[parent]
        stats["mentions"] += entity.get("mentions", 0)
        stats["heat"] += entity.get("heat", 0)
        stats["product_count"] += 1
        stats["products"].append(entity.get("name", ""))
        stats["post_ids"].update(entity.get("post_ids", []))
        
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
            stats["sentiment"] = round(stats["sentiment_weighted_sum"] / stats["sentiment_weight"], 2)
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
    
    return brand_stats


def analyze_competitor_radar(
    target_entity: Optional[dict[str, Any]],
    competitor_entities: list[dict[str, Any]],
    aggregated_entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """竞品雷达分析 (带品牌聚合和自动降级策略)
    
    改进：使用 tags.parent 将同品牌产品聚合后对比品牌整体表现
    """
    if not target_entity or not competitor_entities:
        return {"mode": "none"}
    
    # 1. 按 parent 聚合实体
    # 聚合 Target 品牌
    target_brands = _aggregate_entities_by_parent(aggregated_entities, role_filter="target")
    # 聚合 Competitor 品牌
    competitor_brands = _aggregate_entities_by_parent(aggregated_entities, role_filter="competitor")
    
    # 2. 确定对比对象
    # Target: 优先使用聚合后的品牌，否则使用原实体
    target_parent = _get_entity_parent(target_entity)
    if target_parent in target_brands and target_brands[target_parent]["product_count"] > 1:
        # 品牌下有多个产品，使用聚合数据
        target_data = target_brands[target_parent]
        target_name = f"{target_parent} ({target_data['product_count']}个产品)"
    else:
        # 只有一个产品或没有聚合数据，使用原实体
        target_data = target_entity
        target_name = target_entity["name"]
    
    # Competitor: 优先使用聚合后的品牌
    competitor_parent = _get_entity_parent(competitor_entities[0])
    if competitor_parent in competitor_brands and competitor_brands[competitor_parent]["product_count"] > 1:
        competitor_data = competitor_brands[competitor_parent]
        competitor_name = f"{competitor_parent} ({competitor_data['product_count']}个产品)"
    else:
        competitor_data = competitor_entities[0]
        competitor_name = competitor_entities[0]["name"]
    
    # 3. 检查数据充足性
    has_enough_data = competitor_data.get("mentions", 0) >= 5
    
    if not has_enough_data:
        # Mode B: Bar Chart (降级为简单的正负面占比对比)
        return {
            "mode": "bar",
            "series": [
                {
                    "name": target_name,
                    "sentiment": target_data.get("sentiment", 0),
                    "sentiment_distribution": target_data.get("sentiment_distribution", {}),
                    "products": target_data.get("products", [target_entity["name"]]),
                },
                {
                    "name": competitor_name,
                    "sentiment": competitor_data.get("sentiment", 0),
                    "sentiment_distribution": competitor_data.get("sentiment_distribution", {}),
                    "products": competitor_data.get("products", [competitor_entities[0]["name"]]),
                }
            ]
        }
    
    # Mode A: Radar
    # 5 维雷达：声量、情感、互动、好评率、差评控制
    
    def _get_radar_score(entity: dict, max_mentions: int, max_heat: float) -> list[float]:
        # 1. 声量 (0-1)
        m_score = min(entity.get("mentions", 0) / (max_mentions + 1), 1.0)
        # 2. 情感 (映射 -1~1 到 0~1)
        s_score = (entity.get("sentiment", 0) + 1) / 2
        # 3. 互动
        h_score = min(math.log(entity.get("heat", 0) + 1) / (math.log(max_heat + 1) + 0.1), 1.0)
        
        dist = entity.get("sentiment_distribution", {})
        total = sum(dist.values()) if dist else 1
        # 4. 好评率
        pos_score = dist.get("positive", 0) / total if total > 0 else 0
        # 5. 差评控制 (1 - 差评率)
        neg_ratio = dist.get("negative", 0) / total if total > 0 else 0
        neg_control_score = 1.0 - neg_ratio
        
        return [
            round(m_score, 2),
            round(s_score, 2),
            round(h_score, 2),
            round(pos_score, 2),
            round(neg_control_score, 2)
        ]

    # 计算最大值用于归一化
    max_mentions = max(target_data.get("mentions", 0), competitor_data.get("mentions", 0))
    max_heat = max(target_data.get("heat", 0), competitor_data.get("heat", 0))
    
    return {
        "mode": "radar",
        "dimensions": ["声量影响", "综合情感", "互动热度", "好评率", "差评控制"],
        "series": [
            {
                "name": target_name,
                "data": _get_radar_score(target_data, max_mentions, max_heat),
                "products": target_data.get("products", [target_entity["name"]]),
            },
            {
                "name": competitor_name,
                "data": _get_radar_score(competitor_data, max_mentions, max_heat),
                "products": competitor_data.get("products", [competitor_entities[0]["name"]]),
            }
        ]
    }


# ============================================================================
# 4. KOL 声音提取
# ============================================================================

from src.social_media.analysis.celery_tasks.aggregation.utils import calculate_impact_score

def extract_kol_voices(
    posts_data: list[dict[str, Any]],
    db: Session,
    top_n: int = 5
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
        if not post_id: continue
        
        stmt = select(SocialPost).where(SocialPost.id == post_id)
        post = db.execute(stmt).scalar_one_or_none()
        
        if post:
            deep_res = post_info.get("post_deep_result") or {}
            summary = deep_res.get("summary", "")
            
            results.append({
                "post_id": post.id,
                "author": post.author_name or "未知作者",
                "title": post.title or (post.content[:20] + "..." if post.content else ""),
                "cii": post_info.get("cii", 0),
                "sentiment": post_info.get("sentiment", 0),
                "summary": summary,
                "platform": post.platform.value if hasattr(post.platform, "value") else str(post.platform)
            })
            
    return results
