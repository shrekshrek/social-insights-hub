"""新闻媒体服务层"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.news_media.models import NewsMonitor, NewsTask
from src.news_media.schemas import NewsMonitorCreate, NewsTaskCreate

logger = logging.getLogger(__name__)


async def create_news_monitor(
    db: AsyncSession, data: NewsMonitorCreate, user_id: int
) -> NewsMonitor:
    """创建新闻监测项目"""
    monitor = NewsMonitor(
        name=data.name,
        description=data.description,
        owner_id=user_id,
        search_provider=data.search_provider,
    )
    db.add(monitor)
    await db.flush()
    return monitor


async def create_news_task(
    db: AsyncSession,
    monitor_id: int,
    data: NewsTaskCreate,
    user_id: int,
    strategy_id: int | None = None,
    phase: str | None = None,
) -> NewsTask:
    """创建新闻任务"""
    task = NewsTask(
        name=data.name,
        monitor_id=monitor_id,
        strategy_id=strategy_id,
        keywords=data.keywords,
        phase=phase,
        search_params=data.search_params or {},
        created_by=user_id,
    )
    db.add(task)
    await db.flush()
    return task


async def get_news_tasks_by_strategy(
    db: AsyncSession, strategy_id: int, phase: str | None = None
) -> list[NewsTask]:
    """查询策略的新闻任务"""
    stmt = select(NewsTask).where(NewsTask.strategy_id == strategy_id)
    if phase:
        stmt = stmt.where(NewsTask.phase == phase)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def execute_news_probe(db: AsyncSession, task: NewsTask) -> None:
    """执行新闻探测：SerpAPI metadata 搜索（不抓全文）"""
    try:
        task.status = "running"
        await db.flush()

        # TODO: 调用 SerpAPI Baidu News，max_results=10
        # 解析返回的 title/source/date/snippet
        # 写入 task.analysis_result（结构化摘要）

        task.status = "completed"
        task.articles_count = 10  # 示例
        task.analysis_result = {
            "meta": {"keywords": task.keywords, "articles_count": 10},
            "articles": []  # 简化的元数据列表
        }
        await db.flush()
        logger.info(f"NewsTask {task.id}: probe completed")
    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.flush()
        logger.error(f"NewsTask {task.id}: probe failed: {e}", exc_info=True)
        raise


async def execute_news_collect(db: AsyncSession, task: NewsTask) -> None:
    """执行新闻全量采集：SerpAPI 搜索 + Crawl4AI 抓正文 + LLM 分析"""
    try:
        task.status = "running"
        await db.flush()

        # TODO:
        # 1. SerpAPI 搜索，max_results=30
        # 2. Crawl4AI 批量抓取全文（并发，设超时）
        # 3. 调用 news_analysis_chain
        # 4. 写入 task.analysis_result

        task.status = "completed"
        task.articles_count = 30  # 示例
        task.analysis_result = {
            "meta": {"keywords": task.keywords, "articles_count": 30},
            "insights": {
                "coverage_intensity": "high",
                "key_narratives": [],
                "top_topics": [],
                "target_entities": [],
                "competitor_entities": []
            }
        }
        await db.flush()
        logger.info(f"NewsTask {task.id}: collect completed")
    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await db.flush()
        logger.error(f"NewsTask {task.id}: collect failed: {e}", exc_info=True)
        raise
