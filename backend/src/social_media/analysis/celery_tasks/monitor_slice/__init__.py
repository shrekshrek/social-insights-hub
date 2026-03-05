"""项目级切片流水线（Project Slice）

目录结构参考任务级 `celery_tasks/aggregation/`：
- orchestrator.py: 主编排（Stage2 + Stage3）
- 类目对齐：已内置在 opinion_aggregation.py 的观点归一流程中
- entity_aggregation.py: 实体别名归一与对齐聚合（Stage2-B1）
- opinion_aggregation.py: 观点别名归一与对齐聚合（Stage2-B2）
- drivers.py: 实体属性归纳/聚类与矩阵（Stage2-A1）
- insights.py: 基于对齐结果的派生聚合（如 topic_aspects_aligned_v2）
- summary.py: 整体总结（Stage3 / Analyst）
- utils.py: 通用工具（进度写回、降级规则等）
"""

from .orchestrator import run_monitor_slice_pipeline_sync

__all__ = ["run_monitor_slice_pipeline_sync"]
