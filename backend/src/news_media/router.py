"""新闻媒体 API 路由"""

from typing import Literal

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media import service
from src.news_media.dependencies import (
    validate_news_monitor_exists,
    validate_news_monitor_access,
    validate_news_monitor_owner,
    validate_news_task_access,
)
from src.news_media.models import NewsMonitor, NewsTask
from src.news_media.schemas import (
    NewsArticleRead,
    NewsMonitorCreate,
    NewsMonitorParticipantAssignment,
    NewsMonitorRead,
    NewsMonitorReadWithOwner,
    NewsMonitorUpdate,
    NewsTaskCreate,
    NewsTaskRead,
    NewsTaskReadWithRelations,
)
from src.schemas import MessageResponse, PaginatedResponse

router = APIRouter(prefix="/news-media", tags=["News Media"])


# ==================== Monitor Endpoints ====================


@router.post(
    "/monitors",
    response_model=NewsMonitorRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新闻监测项目",
)
async def create_monitor(
    data: NewsMonitorCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    monitor = await service.create_news_monitor(db, data, current_user.id)
    return monitor


@router.get(
    "/monitors",
    response_model=PaginatedResponse[NewsMonitorReadWithOwner],
    status_code=status.HTTP_200_OK,
    summary="获取新闻监测项目列表",
)
async def list_monitors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    monitors, total = await service.get_news_monitors(
        db, page=page, page_size=page_size,
        participant_id=current_user.id, search=search,
    )
    items = [NewsMonitorReadWithOwner.from_orm_full(m) for m in monitors]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/monitors/{monitor_id}",
    response_model=NewsMonitorReadWithOwner,
    status_code=status.HTTP_200_OK,
    summary="获取新闻监测项目详情",
)
async def get_monitor(
    monitor: NewsMonitor = Depends(validate_news_monitor_access),
):
    return NewsMonitorReadWithOwner.from_orm_full(monitor)


@router.put(
    "/monitors/{monitor_id}",
    response_model=NewsMonitorRead,
    status_code=status.HTTP_200_OK,
    summary="更新新闻监测项目",
)
async def update_monitor(
    data: NewsMonitorUpdate,
    monitor: NewsMonitor = Depends(validate_news_monitor_owner),
    db: AsyncSession = Depends(get_async_db),
):
    updated = await service.update_news_monitor(db, monitor, data)
    return updated


@router.delete(
    "/monitors/{monitor_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除新闻监测项目",
)
async def delete_monitor(
    monitor: NewsMonitor = Depends(validate_news_monitor_owner),
    db: AsyncSession = Depends(get_async_db),
):
    await service.delete_news_monitor(db, monitor)
    return MessageResponse(message=f"监测项目 '{monitor.name}' 已删除")


@router.post(
    "/monitors/{monitor_id}/participants",
    response_model=NewsMonitorReadWithOwner,
    status_code=status.HTTP_200_OK,
    summary="为新闻监测项目添加参与者",
)
async def add_participants(
    data: NewsMonitorParticipantAssignment,
    monitor: NewsMonitor = Depends(validate_news_monitor_owner),
    db: AsyncSession = Depends(get_async_db),
):
    updated = await service.add_participants_to_news_monitor(db, monitor, data.user_ids)
    return NewsMonitorReadWithOwner.from_orm_full(updated)


@router.delete(
    "/monitors/{monitor_id}/participants/{user_id}",
    response_model=NewsMonitorReadWithOwner,
    status_code=status.HTTP_200_OK,
    summary="从新闻监测项目移除参与者",
)
async def remove_participant(
    user_id: int,
    monitor: NewsMonitor = Depends(validate_news_monitor_owner),
    db: AsyncSession = Depends(get_async_db),
):
    updated = await service.remove_participant_from_news_monitor(db, monitor, user_id)
    return NewsMonitorReadWithOwner.from_orm_full(updated)


# ==================== Task Endpoints ====================


@router.get(
    "/tasks",
    response_model=PaginatedResponse[NewsTaskReadWithRelations],
    status_code=status.HTTP_200_OK,
    summary="获取所有新闻任务（跨项目）",
)
async def list_all_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status_filter: Literal["pending", "running", "completed", "failed"] | None = Query(default=None, alias="status"),
    phase: Literal["probe", "collect"] | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(get_current_user),
):
    tasks, total = await service.get_news_tasks(
        db, page=page, page_size=page_size,
        status_filter=status_filter, phase=phase, search=search,
    )
    items = [NewsTaskReadWithRelations.from_orm_full(t) for t in tasks]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "/monitors/{monitor_id}/tasks",
    response_model=NewsTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新闻任务",
)
async def create_task(
    data: NewsTaskCreate,
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    task = await service.create_news_task(db, monitor.id, data, current_user.id, phase=data.phase)
    return task


@router.get(
    "/monitors/{monitor_id}/tasks",
    response_model=PaginatedResponse[NewsTaskReadWithRelations],
    status_code=status.HTTP_200_OK,
    summary="获取监测项目的任务列表",
)
async def list_monitor_tasks(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status_filter: Literal["pending", "running", "completed", "failed"] | None = Query(default=None, alias="status"),
    phase: Literal["probe", "collect"] | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(get_current_user),
):
    tasks, total = await service.get_news_tasks(
        db, page=page, page_size=page_size,
        monitor_id=monitor.id, status_filter=status_filter,
        phase=phase, search=search,
    )
    items = [NewsTaskReadWithRelations.from_orm_full(t) for t in tasks]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/tasks/{task_id}",
    response_model=NewsTaskReadWithRelations,
    status_code=status.HTTP_200_OK,
    summary="获取新闻任务详情",
)
async def get_task(
    task: NewsTask = Depends(validate_news_task_access),
):
    return NewsTaskReadWithRelations.from_orm_full(task)


@router.delete(
    "/tasks/{task_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除新闻任务",
)
async def delete_task(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
):
    await service.delete_news_task(db, task)
    return MessageResponse(message=f"任务 '{task.name}' 已删除")


@router.post(
    "/tasks/{task_id}/execute",
    response_model=NewsTaskRead,
    status_code=status.HTTP_200_OK,
    summary="执行新闻任务",
)
async def execute_task(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    if task.phase == "collect":
        # collect 耗时较长，通过 Celery 异步执行，立即返回 running 状态
        from src.social_media.analysis.jobs.factory import create_analysis_job_async
        from src.social_media.analysis.models import AnalysisType

        # 预创建两个 AnalysisJob（标注 + 洞察），供 AI 分析板块展示
        tagging_job = await create_analysis_job_async(
            db=db,
            news_monitor_id=task.monitor_id,
            news_task_id=task.id,
            user_id=current_user.id,
            analysis_type=AnalysisType.NEWS_TAGGING.value,
            source_count=0,  # 文章数量在任务执行后更新
        )
        insight_job = await create_analysis_job_async(
            db=db,
            news_monitor_id=task.monitor_id,
            news_task_id=task.id,
            user_id=current_user.id,
            analysis_type=AnalysisType.NEWS_INSIGHT.value,
            source_count=0,
        )

        task.status = "running"
        await db.commit()
        await db.refresh(task)

        from src.news_media.celery_tasks import run_news_collect_task
        celery_result = run_news_collect_task.delay(
            task_id=task.id,
            tagging_job_id=tagging_job.id,
            insight_job_id=insight_job.id,
        )

        # 将真实 celery_task_id 绑定到 tagging_job（唯一约束限制只能绑一条）
        tagging_job.celery_task_id = celery_result.id
        await db.commit()
    else:
        await service.execute_news_probe(db, task)
        await db.commit()
    return task


# ==================== Monitor 聚合端点 ====================


@router.get(
    "/monitors/{monitor_id}/aggregated",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="获取监测项目统计聚合（自动计算，无 LLM）",
)
async def get_monitor_aggregated(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(get_current_user),
):
    return await service.get_monitor_aggregated_stats(db, monitor.id)


@router.post(
    "/monitors/{monitor_id}/aggregate",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="触发叙事聚合（运行 news_insight_chain，写入 aggregated_result）",
)
async def run_monitor_aggregate(
    monitor: NewsMonitor = Depends(validate_news_monitor_owner),
    db: AsyncSession = Depends(get_async_db),
    analysis_goal: str = Body(default="", embed=True),
    subject: str = Body(default="", embed=True),
):
    return await service.run_monitor_narrative_aggregate(
        db, monitor, analysis_goal=analysis_goal, subject=subject
    )


# ==================== Article Endpoints ====================


@router.get(
    "/tasks/{task_id}/articles",
    response_model=PaginatedResponse[NewsArticleRead],
    status_code=status.HTTP_200_OK,
    summary="获取任务的文章列表",
)
async def list_task_articles(
    task: NewsTask = Depends(validate_news_task_access),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    relevance: Literal["high", "medium", "low"] | None = Query(default=None),
    source_tier: Literal["tier1", "tier2", "tier3"] | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(get_current_user),
):
    from src.news_media import crud

    skip = (page - 1) * page_size
    articles, total = await crud.get_articles_by_task(
        db, task_id=task.id, skip=skip, limit=page_size,
        relevance=relevance, source_tier=source_tier,
    )
    items = [NewsArticleRead.model_validate(a) for a in articles]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)
