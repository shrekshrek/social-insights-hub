"""聚合分析子模块

负责任务级分析结果的聚合、归一化和洞察派生。

模块结构：
- orchestrator.py: 主聚合函数 aggregate_task_analysis
- entity_aggregation.py: 实体聚合与 LLM 归一化
- opinion_aggregation.py: 观点聚合与 LLM 归一化
- metrics.py: 基础指标计算（CII、NSR、SERP等）
- insights.py: 派生洞察（KANO、场景人群、竞品、KOL）
"""

from .orchestrator import aggregate_task_analysis
from .entity_aggregation import aggregate_entities
from .opinion_aggregation import aggregate_opinions
from .metrics import (
    calculate_cii,
    calculate_cii_for_post,
    calculate_nsr,
    calculate_serp_health,
    calculate_marketing_density,
    calculate_sentiment_conflict,
    calculate_time_distribution,
)
from .insights import (
    derive_context_analysis,
    classify_kano_model,
    analyze_competition,
    extract_kol_voices,
)

__all__ = [
    # Orchestrator
    "aggregate_task_analysis",
    # Entity
    "aggregate_entities",
    # Opinion
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
    "derive_context_analysis",
    "classify_kano_model",
    "analyze_competition",
    "extract_kol_voices",
]
