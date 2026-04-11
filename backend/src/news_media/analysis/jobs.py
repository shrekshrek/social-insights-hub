"""News media source adapter for the analysis module.

封装 news_media 渠道与 analysis 模块之间的所有交互：
- 创建 NEWS_TAGGING AnalysisJob（逐篇标注）
- insight 分析由 NewsSlice 按需触发，不在采集阶段创建 job

调用方：
- src/news_media/tasks/router.py 的 /execute 端点
- src/strategies/service.py 的新闻渠道分支
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.jobs.factory import create_analysis_job_async
from src.jobs.models import AnalysisJob, AnalysisType
from src.news_media.tasks.models import NewsTask


async def create_news_tagging_job(
    db: AsyncSession,
    task: NewsTask,
    user_id: int,
) -> AnalysisJob:
    """为 news collect 任务创建 tagging AnalysisJob。

    返回 tagging_job，供 celery 任务后续填充进度与结果。
    """
    return await create_analysis_job_async(
        db=db,
        news_monitor_id=task.monitor_id,
        news_task_id=task.id,
        user_id=user_id,
        analysis_type=AnalysisType.NEWS_TAGGING.value,
        source_count=0,
    )
