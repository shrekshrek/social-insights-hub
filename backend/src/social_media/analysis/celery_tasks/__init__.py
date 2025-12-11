"""分析模块异步任务

包含所有AI分析相关的Celery任务：
- 任务级初筛任务（screening_tasks）
- 任务级深度分析任务（deep_analysis_tasks）
- 项目级聚类任务（clustering_tasks）
- 项目级竞品分析任务（competitive_tasks）

子模块：
- aggregation/: 任务级分析聚合（实体聚合、观点聚合、指标计算、派生洞察）
"""

from .aggregation import (
    # Orchestrator
    aggregate_task_analysis,
    # Entity
    aggregate_entities,
    # Topic
    aggregate_opinions,
    # Metrics
    calculate_cii,
    calculate_cii_for_post,
    calculate_nsr,
    calculate_serp_health,
    calculate_marketing_density,
    calculate_sentiment_conflict,
    calculate_time_distribution,
    # Insights
    perform_ipa_analysis,
    build_context_graph,
    analyze_competitor_radar,
    classify_kano_model,
    extract_kol_voices,
)

__all__ = [
    # Orchestrator
    "aggregate_task_analysis",
    # Entity
    "aggregate_entities",
    # Topic
    "aggregate_opinions",
    # Metrics
    "calculate_cii",
    "calculate_cii_for_post",
    "calculate_nsr",
    "calculate_serp_health",
    "calculate_marketing_density",
    "calculate_sentiment_conflict",
    "calculate_time_distribution",
    # Insights
    "perform_ipa_analysis",
    "build_context_graph",
    "analyze_competitor_radar",
    "classify_kano_model",
    "extract_kol_voices",
]
