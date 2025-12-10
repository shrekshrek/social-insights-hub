"""派生洞察模块

从 aggregated_entities 和 aggregated_opinions 派生的高级洞察，包含：
1. 产品力诊断 (IPA Analysis)
2. "人-货-场" 关联网络 (Context Graph)
3. 精细化竞品雷达 (Competitor Radar)
4. KANO 需求分层 (KANO Model)
5. KOL 声音提取 (KOL Voices)

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

def perform_ipa_analysis(
    aggregated_entities: list[dict[str, Any]],
    aggregated_opinions: list[dict[str, Any]],
    min_mentions: int = 3
) -> dict[str, Any]:
    """执行 IPA (Importance-Performance Analysis) 产品力诊断
    
    坐标系：
    - X轴 (重要性): mentions (声量)
    - Y轴 (表现): sentiment (情感值 -1 ~ 1)
    
    Args:
        min_mentions: 最小提及次数，过滤小样本噪点
    """
    quadrants = {
        "strength": [],     # Q1 优势区 (High Importance, High Performance)
        "improvement": [],  # Q2 改进区 (High Importance, Low Performance)
        "maintain": [],     # Q3 维持区 (Low Importance, Low Performance)
        "opportunity": []   # Q4 机会区 (Low Importance, High Performance)
    }
    
    # 1. 收集所有属性类实体和话题
    candidates = []
    
    # 从实体中提取属性
    for entity in aggregated_entities:
        # 只关注产品属性类实体
        if entity.get("category") in ["属性", "产品属性"] or entity.get("type") == "产品属性":
            candidates.append(entity)
            
    # 从话题中提取
    # 话题本身通常就是对属性的讨论
    candidates.extend(aggregated_opinions)
    
    if not candidates:
        return {"quadrants": quadrants}
        
    # 2. 计算阈值 (动态计算中位数)
    all_mentions = [c["mentions"] for c in candidates if c["mentions"] >= min_mentions]
    if not all_mentions:
        return {"quadrants": quadrants}
        
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
        
        point = {
            "name": name,
            "x": mentions, # Importance
            "y": round(sentiment, 2), # Performance
            "score": item.get("score", 0),
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
        
    # 按 score 排序
    for key in quadrants:
        quadrants[key].sort(key=lambda x: x["score"], reverse=True)
        
    return {
        "quadrants": quadrants,
        "thresholds": {
            "x": avg_mentions,
            "y": sentiment_threshold
        }
    }


# ============================================================================
# 2. "人-货-场" 关联网络 (Context Graph)
# ============================================================================

def build_context_graph(
    target_entity: Optional[dict[str, Any]],
    aggregated_entities: list[dict[str, Any]],
    aggregated_opinions: list[dict[str, Any]],
    top_n_neighbors: int = 5
) -> dict[str, Any]:
    """构建以 Target 实体为中心的星形关联网络
    
    基于 post_ids 的 Jaccard 相似度计算共现关系。
    """
    if not target_entity:
        return {}
        
    center_name = target_entity["name"]
    center_pids = set(target_entity.get("post_ids", []))
    
    if not center_pids:
        return {"center_node": center_name, "nodes": [], "edges": []}

    nodes = []
    edges = []
    
    # 候选节点池：人群、场景、主要痛点/爽点
    candidates = []
    
    # 1. 提取人群和场景 (来自实体)
    for entity in aggregated_entities:
        if entity["name"] == center_name: continue
        
        cat = entity.get("category", "")
        role = entity.get("role", "")
        
        if cat in ["人群", "场景"] or role in ["Context"]:
            candidates.append({
                "name": entity["name"],
                "type": "audience" if cat == "人群" else "scenario",
                "post_ids": set(entity.get("post_ids", []))
            })
            
    # 2. 提取主要话题 (来自 Top Opinions)
    # 选取 Mentions 较高的 Top 10 话题作为节点
    for topic in aggregated_opinions[:10]:
         candidates.append({
            "name": topic["name"],
            "type": "topic", # 可能是 issue 或 feature，统称 topic
            "sentiment": topic.get("sentiment", 0),
            "post_ids": set(topic.get("post_ids", []))
        })
        
    # 3. 计算 Jaccard 相似度并排序
    # J(A,B) = |A ∩ B| / |A ∪ B|
    # 但对于关联分析，有时 P(B|A) (置信度) 更有意义：在讨论 A (本品) 的时候，有多大概率讨论 B
    # 这里采用一种加权混合：Co-occurrence count * Jaccard
    
    related_nodes = []
    for cand in candidates:
        cand_pids = cand["post_ids"]
        if not cand_pids: continue
        
        intersection = center_pids.intersection(cand_pids)
        union = center_pids.union(cand_pids)
        
        co_occurrence = len(intersection)
        if co_occurrence < 1: continue # 至少共现1次
        
        jaccard = co_occurrence / len(union)
        
        # 权重设计：偏向于共现次数多的，同时参考关联紧密度
        weight = jaccard 
        
        related_nodes.append({
            "name": cand["name"],
            "type": cand["type"],
            "weight": weight,
            "co_occurrence": co_occurrence,
            "sentiment": cand.get("sentiment"),
            "post_ids": list(intersection) # 仅保留共现的帖子用于溯源，而非该节点的所有帖子
        })
        
    # 按权重排序取 Top N
    related_nodes.sort(key=lambda x: x["weight"], reverse=True)
    top_nodes = related_nodes[:top_n_neighbors]
    
    # 格式化输出
    for node in top_nodes:
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

def analyze_competitor_radar(
    target_entity: Optional[dict[str, Any]],
    competitor_entities: list[dict[str, Any]],
    aggregated_entities: list[dict[str, Any]]
) -> dict[str, Any]:
    """竞品雷达分析 (带自动降级策略)
    
    对比维度：从 aggregated_entities 的属性中提取通用维度 (parent 或 category)
    """
    if not target_entity or not competitor_entities:
        return {"mode": "none"}
        
    # 取 Top 1 竞品
    top_competitor = competitor_entities[0]
    
    # 1. 定义对比维度
    # 尝试提取两者共有的属性维度
    # 这里简化处理，预定义几个常见维度，或者根据 entity.features/issues 动态聚合
    # 由于 aggregated_entities 结构中 features 是列表，我们需要反查属性的 parent 类别
    # 这种反查比较复杂，这里采用 simplified 策略：
    # 检查两个实体的 sentiment, heat, 以及是否有特定的属性词
    
    # 策略升级：Mode A (Radar) 需要足够的数据支撑
    # 检查是否有足够的 mentions
    has_enough_data = top_competitor.get("mentions", 0) >= 5
    
    if not has_enough_data:
        # Mode B: Bar Chart (降级为简单的正负面占比对比)
        return {
            "mode": "bar",
            "series": [
                {
                    "name": target_entity["name"],
                    "sentiment": target_entity.get("sentiment", 0),
                    "sentiment_distribution": target_entity.get("sentiment_distribution", {})
                },
                {
                    "name": top_competitor["name"],
                    "sentiment": top_competitor.get("sentiment", 0),
                    "sentiment_distribution": top_competitor.get("sentiment_distribution", {})
                }
            ]
        }
    
    # Mode A: Radar (尝试构建维度)
    # 这里我们模拟几个核心维度，实际项目中应该基于 Tag 体系聚合
    # 临时逻辑：使用 sentiment_distribution 的拆解作为维度替代
    # 或者如果后续有属性维度的归一化数据，可以在这里扩展
    
    # 目前使用 5 维基础雷达：
    # 1. 声量 (Mentions - Log归一化)
    # 2. 情感 (Sentiment - 归一化到 0-1)
    # 3. 互动 (Heat - Log归一化)
    # 4. 好评度 (Positive Ratio)
    # 5. 差评度 (Negative Ratio - 反向，越低越好 -> 1-ratio)
    
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
    max_mentions = max(target_entity.get("mentions", 0), top_competitor.get("mentions", 0))
    max_heat = max(target_entity.get("heat", 0), top_competitor.get("heat", 0))
    
    return {
        "mode": "radar",
        "dimensions": ["声量影响", "综合情感", "互动热度", "好评率", "差评控制"],
        "series": [
            {
                "name": target_entity["name"],
                "data": _get_radar_score(target_entity, max_mentions, max_heat)
            },
            {
                "name": top_competitor["name"],
                "data": _get_radar_score(top_competitor, max_mentions, max_heat)
            }
        ]
    }


# ============================================================================
# 4. KANO 需求模型 (KANO Model)
# ============================================================================

def classify_kano_model(
    aggregated_opinions: list[dict[str, Any]],
    aggregated_entities: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """新版 KANO 模型
    
    分类逻辑：
    1. Must-be (基本型): 
       - 来源: issues (负面痛点)
       - 特征: mentions 高 (Top 20%), 情感极负
    2. One-dimensional (期望型):
       - 来源: features & opinions
       - 特征: mentions 中高, 情感偏正
    3. Attractive (兴奋型):
       - 来源: features 或 expectations
       - 特征: mentions 低 (3-5次) 但 sentiment 极高 (>0.8)
    """
    
    must_be = []
    one_dimensional = []
    attractive = []
    
    # 辅助函数：标准化 item 结构
    def _make_item(source_item: dict, source_type: str) -> dict:
        return {
            "name": source_item.get("name") or source_item.get("text"), # 兼容 opinion 和 feature 结构
            "score": source_item.get("score", 0),
            "mentions": source_item.get("mentions") or source_item.get("count", 0),
            "sentiment": source_item.get("sentiment", 0),
            "source_type": source_type,
            "post_ids": list(source_item.get("post_ids", [])) # 支持溯源
        }

    # 1. 处理 aggregated_opinions (主体数据)
    # 计算 Mentions 的 80 分位数
    mentions_list = [op["mentions"] for op in aggregated_opinions]
    if not mentions_list:
        return {"must_be": [], "one_dimensional": [], "attractive": []}
        
    mentions_list.sort()
    high_mention_threshold = mentions_list[int(len(mentions_list) * 0.8)] if len(mentions_list) > 5 else 2
    
    for op in aggregated_opinions:
        item = _make_item(op, "opinion")
        mentions = item["mentions"]
        sentiment = item["sentiment"]
        
        # Must-be: 高频负面
        if mentions >= high_mention_threshold and sentiment <= -0.5:
            must_be.append(item)
        # Attractive: 低频高赞
        elif 3 <= mentions < high_mention_threshold and sentiment >= 0.8:
            attractive.append(item)
        # One-dimensional: 中高频正面
        elif mentions >= 3 and sentiment > 0:
            one_dimensional.append(item)
            
    # 2. 补充来自 aggregated_entities 的 features/issues 信息
    # 这部分可能与 opinion 重叠，简单去重
    existing_names = {i["name"] for i in must_be + one_dimensional + attractive}
    
    # 遍历所有实体的 features/issues 会比较多，这里只取 aggregated_entities 中 Top 实体的属性
    # 简化处理：假设 aggregated_opinions 已经包含了大部分核心观点
    # 如果 opinion 覆盖不足，可以开启以下逻辑
    
    # ... (省略实体属性补充逻辑，避免数据冗余) ...
    
    # 排序
    must_be.sort(key=lambda x: x["mentions"], reverse=True)
    one_dimensional.sort(key=lambda x: x["score"], reverse=True)
    attractive.sort(key=lambda x: x["sentiment"], reverse=True) # 兴奋点按情感排序
    
    return {
        "must_be": must_be[:10],
        "one_dimensional": one_dimensional[:10],
        "attractive": attractive[:10]
    }


# ============================================================================
# 5. KOL 声音提取 (Legacy - Keep)
# ============================================================================

def extract_kol_voices(
    posts_data: list[dict[str, Any]],
    db: Session,
    top_n: int = 5
) -> list[dict[str, Any]]:
    """提取 KOL (关键意见领袖) 的声音"""
    # 按 CII 排序
    sorted_posts = sorted(posts_data, key=lambda x: x.get("cii", 0), reverse=True)
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
                "platform": post.platform
            })
            
    return results
