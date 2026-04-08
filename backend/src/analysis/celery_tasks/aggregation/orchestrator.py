"""任务级分析聚合编排器 (Task Analysis Aggregator Orchestrator)

在 Finalizer 中调用，对任务下的所有原文分析结果进行聚合计算。

注意：本项目采用双重情感评分体系（详见设计文档 §1.1）
- 宏观指标 (NSR, SERP, 四象限): 基于初筛情感 (-2 ~ +2)
- 微观指标 (实体, 观点): 基于深度分析情感 (-1 ~ +1)

本模块功能：
1. 四象限数据生成
2. 主聚合函数 aggregate_task_analysis
3. 空结果结构 _empty_result

已拆分的聚合模块：
- metrics.py: 基础指标计算（CII、NSR、SERP等）
- entity_aggregation.py: 实体聚合与LLM归一化 → aggregated_entities
- opinion_aggregation.py: 观点聚合与LLM归一化 → aggregated_opinions
- insights.py: 派生洞察（IPA、关联网络、竞品雷达、KOL）

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis.models import PostAnalysis, AnalysisType
from src.analysis.constants import SPAM_HIGH_THRESHOLD
from src.analysis.jobs import (
    create_analysis_job_sync,
    complete_analysis_job_sync,
    start_analysis_job_sync,
)
from src.social_media.tasks.models import SocialPost, SocialTask as SocialTask
from .metrics import (
    calculate_cii_for_post,
    calculate_nsr,
    calculate_serp_health,
    calculate_marketing_density,
    calculate_sentiment_conflict,
    calculate_time_distribution,
)
from .entity_aggregation import aggregate_entities
from .opinion_aggregation import aggregate_opinions
from .spam_distribution import build_spam_distributions, _build_spam_map
from .insights import (
    perform_ipa_analysis,
    build_context_graph,
    analyze_competitor_radar,
    extract_kol_voices,
)

logger = logging.getLogger(__name__)


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
        posts_data: 原文数据列表

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

        quadrant_data.append(
            {
                "post_id": post_id,
                "x": sentiment,  # 情感分
                "y": round(cii, 2),  # CII
                "quadrant": quadrant,
                "label": label,
            }
        )

    return quadrant_data


def get_quadrant_summary(quadrant_data: list[dict[str, Any]]) -> dict[str, int]:
    """统计各象限的原文数量"""
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
    monitor_id: int | None = None,
    user_id: int | None = None,
    enable_entity_normalization: bool = True,
    entity_job_id: int | None = None,
    opinion_job_id: int | None = None,
    spam_threshold: float = SPAM_HIGH_THRESHOLD,
) -> dict[str, Any]:
    """执行任务级分析聚合

    Args:
        db: 数据库会话
        task_id: 任务ID
        monitor_id: 项目ID（用于创建 AnalysisJob 记录）
        user_id: 用户ID（用于创建 AnalysisJob 记录）
        enable_entity_normalization: 是否启用 LLM 实体归一化（会增加成本）
        entity_job_id: 预创建的实体归一化 AnalysisJob ID
        opinion_job_id: 预创建的观点归一化 AnalysisJob ID
        spam_threshold: spam 分组阈值（默认 6.0，>= 此值为高广告组）

    Returns:
        dict: 聚合结果，存入 AnalysisJob.result_data
    """
    logger.info("开始聚合任务 %s 的分析结果", task_id)

    # 0. 获取任务信息（关键词用于主体过滤）
    task_stmt = select(SocialTask).where(SocialTask.id == task_id)
    task = db.execute(task_stmt).scalar_one_or_none()

    task_keywords: list[str] = []
    if task and task.keywords:
        # 关键词可能是逗号分隔的字符串
        task_keywords = [k.strip() for k in task.keywords.split(",") if k.strip()]
        logger.info("任务 %s 关键词: %s", task_id, task_keywords)

    # 1. 查询所有原文及其分析结果
    stmt = (
        select(SocialPost, PostAnalysis)
        .outerjoin(PostAnalysis, PostAnalysis.post_id == SocialPost.id)
        .where(SocialPost.task_id == task_id)
        .where(SocialPost.is_deleted.is_(False))
    )
    result = db.execute(stmt)
    rows = result.all()

    if not rows:
        logger.warning("任务 %s 没有原文数据", task_id)
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
            "value_score": None,  # 用于影响力计算
            "published_at": post.published_at,  # 用于时效性分布
            "post_deep_result": None,
            "comment_deep_result": None,
        }

        if analysis:
            # 基础数据回填
            if analysis.spam_score is not None:
                screened_posts += 1
                post_info["sentiment"] = analysis.sentiment
                post_info["spam_score"] = analysis.spam_score
                post_info["value_score"] = analysis.value_score

            if analysis.post_deep_result:
                deep_analyzed_posts += 1
                post_info["post_deep_result"] = analysis.post_deep_result

                # 【Unified Sentiment】优先使用深度分析的情感值覆盖初筛值
                # 检查深度分析中是否包含情感倾向
                # 如果是 Entity Sentiment Aggregation 后的结果会更好，但这里直接用 post_deep_result.sentiment
                # 如果结构中没有 sentiment 字段，则尝试计算
                deep_sentiment = analysis.post_deep_result.get("sentiment")
                if deep_sentiment is not None:
                    post_info["sentiment"] = deep_sentiment

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
    marketing_stats = calculate_marketing_density(posts_data, threshold=spam_threshold)

    # 舆论反差度
    sentiment_conflict = calculate_sentiment_conflict(posts_data)

    # 4. 时效性分布 (§4.2)
    time_distribution = calculate_time_distribution(posts_data)

    # 5. 实体聚合 + 观点聚合（并行执行）
    # 使用预创建的 AnalysisJob（由 service.py 创建），或创建新的（向后兼容）
    entity_job = None
    opinion_job = None
    if enable_entity_normalization:
        if entity_job_id:
            # 使用预创建的 job，更新状态为 processing
            entity_job = start_analysis_job_sync(db, entity_job_id)
        elif monitor_id and user_id:
            # 向后兼容：内部创建 job
            entity_job = create_analysis_job_sync(
                db=db,
                social_monitor_id=monitor_id,
                social_task_id=task_id,
                user_id=user_id,
                analysis_type=AnalysisType.ENTITY_NORMALIZATION.value,
                source_count=len(posts_data),
                status="processing",
            )

        if opinion_job_id:
            # 使用预创建的 job，更新状态为 processing
            opinion_job = start_analysis_job_sync(db, opinion_job_id)
        elif monitor_id and user_id:
            # 向后兼容：内部创建 job
            opinion_job = create_analysis_job_sync(
                db=db,
                social_monitor_id=monitor_id,
                social_task_id=task_id,
                user_id=user_id,
                analysis_type=AnalysisType.OPINION_NORMALIZATION.value,
                source_count=len(posts_data),
                status="processing",
            )

    # 并行执行实体聚合和话题聚合（两者互相独立）
    entity_stats = {}
    topic_stats = {}

    def run_entity_aggregation():
        return aggregate_entities(
            posts_data,
            task_keywords=task_keywords,
            enable_llm_normalization=enable_entity_normalization,
            spam_threshold=spam_threshold,
        )

    def run_topic_aggregation():
        return aggregate_opinions(
            posts_data,
            # task_keywords=task_keywords, # 话题聚合暂不需要 task_keywords
            # enable_llm_normalization=enable_entity_normalization,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_entity = executor.submit(run_entity_aggregation)
        future_topic = executor.submit(run_topic_aggregation)

        # 等待两个任务完成
        for future in as_completed([future_entity, future_topic]):
            try:
                if future == future_entity:
                    entity_stats = future.result()
                    logger.info("[并行聚合] 实体聚合完成")
                else:
                    topic_stats = future.result()
                    logger.info("[并行聚合] 观点聚合完成")
            except Exception as e:
                logger.error("[并行聚合] 聚合任务失败: %s", e)
                raise

    # 更新 AnalysisJob 记录
    # 归一化是一次性任务，完成后 analyzed_count = source_count
    if entity_job:
        complete_analysis_job_sync(
            db=db,
            job=entity_job,
            analyzed_count=entity_job.source_count,
            token_usage=entity_stats.get("llm_token_stats"),
        )
    if opinion_job:
        complete_analysis_job_sync(
            db=db,
            job=opinion_job,
            analyzed_count=opinion_job.source_count,
            token_usage=topic_stats.get("llm_token_stats"),
        )

    # 7. 四象限数据
    quadrant_data = generate_quadrant_data(posts_data)
    quadrant_summary = get_quadrant_summary(quadrant_data)

    # 8. 高级派生分析 (基于 DERIVED_ANALYSIS_DESIGN.md)
    aggregated_entities = entity_stats.get("aggregated_entities", [])
    aggregated_opinions = topic_stats.get("opinions", [])

    # 获取分类后的实体（展示用简化格式）
    target_entities = entity_stats.get("target_entities", [])
    competitor_entities = entity_stats.get("competitor_entities", [])

    # 从 aggregated_entities 中找到完整的 Top 1 Target 实体（包含完整的 features/issues）
    # 展示用的 target_entities 只有字符串数组，缺少 post_ids
    top_target_full = None
    if target_entities:
        top_target_name = target_entities[0].get("name")
        for entity in aggregated_entities:
            if entity.get("name") == top_target_name:
                top_target_full = entity
                break

    # 从 aggregated_entities 中找到完整的 competitor 实体
    competitor_entities_full = []
    for comp in competitor_entities:
        comp_name = comp.get("name")
        for entity in aggregated_entities:
            if entity.get("name") == comp_name:
                competitor_entities_full.append(entity)
                break

    # §5 派生洞察计算 - 提前构建 spam_map 以支持维度筛选
    spam_map = _build_spam_map(posts_data, threshold=spam_threshold)

    # (1) 关联网络 (Context Graph) - 以 Top 1 Target 实体为中心
    # 节点包括：人群、场景、产品属性(features/issues)、话题、竞品
    context_graph = build_context_graph(
        top_target_full, aggregated_opinions, competitor_entities_full,
        spam_map=spam_map
    )

    # (2) 产品力诊断 (IPA) - 使用 opinions + target 实体的 features/issues
    ipa_result = perform_ipa_analysis(aggregated_opinions, top_target_full)

    # (3) 竞品雷达 (Competitor Radar)
    competitor_radar = analyze_competitor_radar(
        top_target_full, competitor_entities_full, aggregated_entities,
        spam_map=spam_map, posts_data=posts_data
    )

    # (4) KOL 声音提取
    kol_voices = extract_kol_voices(posts_data, db, top_n=10)

    # 9. NSR 按 spam 分组拆分
    screened_posts_list = [
        p for p in posts_data if p.get("spam_score") is not None
    ]
    nsr_by_spam = None
    if screened_posts_list:
        high_spam_posts = [
            p for p in screened_posts_list if p["spam_score"] >= spam_threshold
        ]
        low_spam_posts = [
            p for p in screened_posts_list if p["spam_score"] < spam_threshold
        ]
        nsr_by_spam = {
            "high": calculate_nsr(high_spam_posts),
            "low": calculate_nsr(low_spam_posts),
        }

    # 10. Spam 分布附加（全模块）
    time_dist_list = time_distribution.get("distribution", [])

    # 提取 IPA 所有象限的点
    ipa_all_points = []
    if ipa_result and ipa_result.get("quadrants"):
        for quadrant_list in ipa_result["quadrants"].values():
            if isinstance(quadrant_list, list):
                ipa_all_points.extend(quadrant_list)

    competitor_series = competitor_radar.get("all", {}).get("series", [])

    spam_config = build_spam_distributions(
        aggregated_entities=aggregated_entities,
        aggregated_opinions=aggregated_opinions,
        quadrant_data=quadrant_data,
        kol_voices=kol_voices,
        ipa_points=ipa_all_points,
        competitor_series=competitor_series,
        time_distribution=time_dist_list,
        posts_data=posts_data,
        threshold=spam_threshold,
    )

    # 传播 spam_distribution 到 insights 展示列表
    entity_spam_lookup = {
        e["name"]: e.get("spam_distribution") for e in aggregated_entities
    }
    for e in entity_stats.get("top_entities", []):
        e["spam_distribution"] = entity_spam_lookup.get(e["name"])
    for e in target_entities:
        e["spam_distribution"] = entity_spam_lookup.get(e["name"])
    for e in competitor_entities:
        e["spam_distribution"] = entity_spam_lookup.get(e["name"])

    opinion_spam_lookup = {
        o["name"]: o.get("spam_distribution") for o in aggregated_opinions
    }
    for o in topic_stats.get("opinions", []):
        o["spam_distribution"] = opinion_spam_lookup.get(o["name"])

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
            "nsr_by_spam": nsr_by_spam,
        },
        "charts": {
            # 保留完整象限列表以便前端反向追溯原文 (宏观概览)
            "quadrant": quadrant_data,
            "quadrant_summary": quadrant_summary,
            "time_distribution": time_dist_list,
            "time_distribution_skipped": time_distribution.get(
                "skipped_count", 0
            ),  # 无发布时间的原文数
            # 新增图表
            "ipa_analysis": ipa_result,
            "competitor_radar": competitor_radar,
            "context_graph": context_graph,
        },
        "freshness": time_distribution.get("freshness", {}),
        "insights": {
            # 实体分类（§4.3 主体过滤结果）
            "top_entities": entity_stats.get("top_entities", []),
            "target_entities": target_entities,
            "competitor_entities": competitor_entities,
            # 话题统计（原观点统计）
            "top_topics": topic_stats.get(
                "opinions", []
            ),  # 返回所有聚合后的观点，由前端进行正负面筛选
            # KOL 声音
            "kol_voices": kol_voices,
        },
        # 原始融合数据（用于后续项目级分析/深挖；不要求下发给前端）
        "aggregated_entities": aggregated_entities,
        "aggregated_opinions": aggregated_opinions,
        # Spam 分组配置
        "spam_config": spam_config,
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
    """返回空结果结构（与正常结果保持一致）"""
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
            "nsr_by_spam": None,
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
            "time_distribution_skipped": 0,
            # 新增图表（与正常结果一致，3 层结构）
            "ipa_analysis": {"quadrants": {}, "thresholds": {"x": 0, "y": 0}},
            "competitor_radar": {
                "all": {"mode": "none"},
                "organic": {"mode": "none"},
                "promo": {"mode": "none"},
            },
            "context_graph": {
                "all": {"center_node": None, "nodes": [], "edges": []},
                "organic": {"center_node": None, "nodes": [], "edges": []},
                "promo": {"center_node": None, "nodes": [], "edges": []},
            },
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
            "top_topics": [],
            "kol_voices": [],
        },
        # 原始融合数据（与正常结果字段名一致）
        "aggregated_entities": [],
        "aggregated_opinions": [],
        # Spam 分组配置
        "spam_config": None,
    }
