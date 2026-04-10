"""跨渠道 AnalysisJob 基础设施

唯一真正的跨渠道"分析"共享组件：记录所有渠道的 LLM 调用、追踪成本/进度/状态。

依赖方向：
- src/jobs/ 不依赖任何渠道模块（TYPE_CHECKING 下的 relationship hint 除外）
- src/social_media, src/news_media, src/strategies, src/knowledge_base 等渠道模块均可 from src.jobs import

参见 docs/adr-001-channel-local-analysis.md。
"""

from .factory import (
    create_analysis_job_sync,
    create_analysis_job_async,
    complete_analysis_job_sync,
    start_analysis_job_sync,
)
from .crud import (
    get_analysis_jobs,
    get_analysis_job,
    get_analysis_progress,
    cancel_analysis_job,
    delete_analysis_job,
    set_celery_task_id,
)
from .models import AnalysisJob, AnalysisType, AnalysisStatus
from .schemas import (
    CallDetail,
    TokenUsageSummary,
    TokenUsageStats,
    AnalysisJobCreate,
    AnalysisJobUpdate,
    AnalysisJobResponse,
    AnalysisJobListResponse,
    AnalysisProgressResponse,
)

__all__ = [
    # Models
    "AnalysisJob",
    "AnalysisType",
    "AnalysisStatus",
    # Factory
    "create_analysis_job_sync",
    "create_analysis_job_async",
    "complete_analysis_job_sync",
    "start_analysis_job_sync",
    # CRUD
    "get_analysis_jobs",
    "get_analysis_job",
    "get_analysis_progress",
    "cancel_analysis_job",
    "delete_analysis_job",
    "set_celery_task_id",
    # Schemas
    "CallDetail",
    "TokenUsageSummary",
    "TokenUsageStats",
    "AnalysisJobCreate",
    "AnalysisJobUpdate",
    "AnalysisJobResponse",
    "AnalysisJobListResponse",
    "AnalysisProgressResponse",
]
