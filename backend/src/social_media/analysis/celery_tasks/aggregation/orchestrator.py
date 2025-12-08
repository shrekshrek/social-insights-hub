"""任务级分析聚合编排器 (Task Analysis Aggregator Orchestrator)

在 Finalizer 中调用，对任务下的所有帖子分析结果进行聚合计算。

注意：本项目采用双重情感评分体系（详见设计文档 §1.1）
- 宏观指标 (NSR, SERP, 四象限): 基于初筛情感 (-2 ~ +2)
- 微观指标 (实体, 观点, KANO): 基于深度分析情感 (-1 ~ +1)

本模块功能：
1. 四象限数据生成
2. 主聚合函数 aggregate_task_analysis
3. 空结果结构 _empty_result

已拆分的聚合模块：
- metrics.py: 基础指标计算（CII、NSR、SERP等）
- entity_aggregation.py: 实体聚合与LLM归一化 → aggregated_entities
- opinion_aggregation.py: 观点聚合与LLM归一化 → aggregated_opinions
- insights.py: 派生洞察（KANO、场景人群、竞品、KOL）

参考设计文档: docs/analysis_design/TASK_ANALYSIS_DETAIL.md
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.social_media.analysis.models import PostAnalysis, AnalysisType
from src.social_media.analysis.jobs import (
    create_analysis_job_sync,
    complete_analysis_job_sync,
)
from src.social_media.tasks.models import SocialPost, DataTask
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
from .insights import (
    derive_context_analysis,
    classify_kano_model,
    analyze_competition,
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
    project_id: int | None = None,
    user_id: int | None = None,
    enable_entity_normalization: bool = True,
) -> dict[str, Any]:
    """执行任务级分析聚合

    Args:
        db: 数据库会话
        task_id: 任务ID
        project_id: 项目ID（用于创建 AnalysisJob 记录）
        user_id: 用户ID（用于创建 AnalysisJob 记录）
        enable_entity_normalization: 是否启用 LLM 实体归一化（会增加成本）

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

    # 5. 实体聚合 + 观点聚合（并行执行）
    # 如果提供了 project_id 和 user_id，创建 AnalysisJob 记录
    entity_job = None
    opinion_job = None
    if project_id and user_id and enable_entity_normalization:
        entity_job = create_analysis_job_sync(
            db=db,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type=AnalysisType.ENTITY_NORMALIZATION.value,
            source_count=len(posts_data),
            status="processing",
        )
        opinion_job = create_analysis_job_sync(
            db=db,
            project_id=project_id,
            task_id=task_id,
            user_id=user_id,
            analysis_type=AnalysisType.TOPIC_NORMALIZATION.value,
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
                    logger.info(f"[并行聚合] 实体聚合完成")
                else:
                    topic_stats = future.result()
                    logger.info(f"[并行聚合] 观点聚合完成")
            except Exception as e:
                logger.error(f"[并行聚合] 聚合任务失败: {e}")
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

    # 8. KANO 需求分层 (§4.5.3) - 基于话题聚合数据 (Topic as 'feature/issue')
    # 注意: KANO 模型原先基于 opinion_stats，现在可能需要适配
    # 暂时传入 topic_stats，但 KANO 分类器可能需要调整
    kano_model = classify_kano_model(topic_stats)

    # 9. 场景与人群画像 (§4.5.4) - 从 aggregated_entities 派生
    aggregated_entities = entity_stats.get("aggregated_entities", [])
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
            # 保留完整象限列表以便前端反向追溯帖子
            "quadrant": quadrant_data,
            "quadrant_summary": quadrant_summary,
            "time_distribution": time_distribution.get("distribution", []),
        },
        "freshness": time_distribution.get("freshness", {}),
        "insights": {
            # 实体分类（§4.3 主体过滤结果）
            "top_entities": entity_stats.get("top_entities", []),
            "target_entities": entity_stats.get("target_entities", []),
            "competitor_entities": entity_stats.get("competitor_entities", []),
            # 话题统计（原观点统计）
            "top_topics": topic_stats.get("topics", [])[:10], # 取 Top 10 话题
            "top_issues": [t for t in topic_stats.get("topics", []) if t.get("sentiment") == -1][:10],
            "top_features": [t for t in topic_stats.get("topics", []) if t.get("sentiment") == 1][:10],
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
        "aggregated_entities": entity_stats.get("aggregated_entities", []),
        "aggregated_topics": topic_stats.get("topics", []), # 原 aggregated_opinions
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
        "aggregated_entities": [],
        "aggregated_opinions": [],
    }
