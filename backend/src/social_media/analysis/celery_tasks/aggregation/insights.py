"""派生洞察模块

从 aggregated_entities 和 aggregated_opinions 派生的高级洞察：
- 场景与人群画像 (derive_context_analysis)
- KANO 需求分层 (classify_kano_model)
- 竞品分析 (analyze_competition)
- KOL 声音提取 (extract_kol_voices)

设计原则：
- **小样本优先**: 适应 100 篇左右的小样本数据，避免过度复杂的统计推断。
- **定性优于定量**: 提供“发现线索”而非“统计报表”，利用 post_ids 进行集合运算。
- **结构化复用**: 充分利用 aggregated_entities 和 aggregated_opinions 的清洗成果。

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md
"""

import logging
from typing import Any, List, Dict
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.social_media.tasks.models import SocialPost

logger = logging.getLogger(__name__)


# ============================================================================
# 场景与人群画像聚合 (§4.5.4) - 从 aggregated_entities 派生
# ============================================================================

def derive_context_analysis(
    aggregated_entities: list[dict[str, Any]],
    top_n: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """从 aggregated_entities 派生场景与人群画像
    
    直接从归一化后的实体中提取 Scenarios 和 Audience，并按热度排序。
    不做复杂的交叉分析，但保留 post_ids 以支持前端反查。
    """
    scenarios = []
    audiences = []
    
    # 提取所有场景和人群实体
    # aggregated_entities 中 type 可能为 "场景" 或 "人群"
    # 或者通过 tags.category 判断
    # 但更直接的是利用 aggregated_entities 结构中的 scenarios/audience 字段
    # 注意：aggregated_entities 是以 Entity 为核心的，我们需要的是以 Scenario/Audience 为核心的聚合
    
    # 重新聚合：Term -> Info
    scenario_map: Dict[str, Dict] = {}
    audience_map: Dict[str, Dict] = {}
    
    for entity in aggregated_entities:
        # 1. 聚合 scenarios 字段
        if entity.get("scenarios"):
            for item in entity["scenarios"]:
                text = item["text"]
                pids = item["post_ids"]
                if text not in scenario_map:
                    scenario_map[text] = {"label": text, "post_ids": set(), "heat": 0.0}
                scenario_map[text]["post_ids"].update(pids)
                # 简单估算热度：每个提及算 1 分，或者累加 entity 的 heat (不准确)
                # 这里直接用提及数作为简单热度，因为 post_ids 已经去重
                
        # 2. 聚合 audience 字段
        if entity.get("audience"):
            for item in entity["audience"]:
                text = item["text"]
                pids = item["post_ids"]
                if text not in audience_map:
                    audience_map[text] = {"label": text, "post_ids": set(), "heat": 0.0}
                audience_map[text]["post_ids"].update(pids)

    def _format_list(source_map: Dict[str, Dict]) -> List[Dict]:
        result = []
        for label, data in source_map.items():
            mentions = len(data["post_ids"])
            if mentions < 1: continue
            
            result.append({
                "label": label,
                "heat": float(mentions), # 简化：直接用声量作为热度
                "mentions": mentions,
                "post_ids": list(data["post_ids"])
            })
        return sorted(result, key=lambda x: x["mentions"], reverse=True)[:top_n]

    return {
        "scenarios": _format_list(scenario_map),
        "audiences": _format_list(audience_map),
    }


# ============================================================================
# KANO 需求分层 (§4.5.3) - 简化版
# ============================================================================

def classify_kano_model(
    aggregated_opinions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """产品特性分类 (简化版 KANO)
    
    基于 aggregated_opinions 的情感和热度进行直观分类。
    不再区分复杂的“期望型/魅力型”，而是简化为用户最关心的三类点。
    """
    
    # 定义容器
    pain_points = []   # 痛点 (Issues): 负面评价
    delighters = []    # 爽点 (Delighters): 正面评价
    basics = []        # 关注点 (Basics): 热度高但情感中性 (大家都在讨论的参数/配置)

    for op in aggregated_opinions:
        # 过滤掉非产品相关的观点 (可选，根据 category 判断)
        # 这里假设所有 opinion 都是相关的
        
        sentiment = op.get("sentiment", 0)
        heat = op.get("heat", 0)
        item = {
            "label": op["name"], # 统一使用 name
            "heat": heat,
            "mentions": op["mentions"],
            "sentiment": sentiment,
            "category": op.get("category", "其他"),
            "post_ids": op["post_ids"]
        }
        
        if sentiment <= -0.5:
            pain_points.append(item)
        elif sentiment >= 0.5:
            delighters.append(item)
        else:
            # 中性观点，如果热度够高才算 Basic
            if op["mentions"] >= 2: # 至少提及2次
                basics.append(item)

    # 排序并截取 Top 10
    pain_points.sort(key=lambda x: x["heat"], reverse=True)
    delighters.sort(key=lambda x: x["heat"], reverse=True)
    basics.sort(key=lambda x: x["heat"], reverse=True)

    return {
        "must_be": pain_points[:10],       # 对应 痛点/急需改进
        "attractive": delighters[:10],     # 对应 爽点/卖点
        "one_dimensional": basics[:10],    # 对应 基础关注/热议参数
    }


# ============================================================================
# 竞品分析
# ============================================================================

def analyze_competition(
    aggregated_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """竞品分析 (简化版)
    
    仅提取被标记为 COMPETITOR 的实体，并按声量排序。
    移除复杂的维度级情感对比。
    """
    competitors = []
    
    for entity in aggregated_entities:
        # 检查是否为竞品 (通过 tags.role 或 之前的 role 字段兼容)
        is_competitor = False
        if entity.get("tags", {}).get("role") == "COMPETITOR":
            is_competitor = True
        
        if is_competitor:
            competitors.append({
                "name": entity["name"],
                "heat": entity["heat"],
                "mentions": entity["mentions"],
                "sentiment": entity["sentiment"],
                "post_ids": entity["post_ids"]
            })
            
    # 按声量排序
    competitors.sort(key=lambda x: x["mentions"], reverse=True)
    
    return {
        "top_competitors": competitors[:10],
        # 保留汇总字段结构，但填入默认值或简单统计
        "comparison_sentiment": 0.0, 
        "competitor_count": len(competitors)
    }


# ============================================================================
# KOL 声音提取
# ============================================================================

def extract_kol_voices(
    posts_data: list[dict[str, Any]],
    db: Session,
    top_n: int = 5
) -> list[dict[str, Any]]:
    """提取 KOL (关键意见领袖) 的声音
    
    逻辑：
    1. 识别高影响力帖子 (CII Top N)
    2. 提取其核心观点摘要
    """
    # 按 CII 排序
    sorted_posts = sorted(posts_data, key=lambda x: x.get("cii", 0), reverse=True)
    top_posts = sorted_posts[:top_n]
    
    results = []
    for post_info in top_posts:
        post_id = post_info.get("post_id")
        if not post_id: continue
        
        # 查询帖子详情 (为了获取作者名和标题)
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
