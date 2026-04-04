"""新闻媒体 API 路由"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media import service
from src.news_media.dependencies import (
    validate_news_monitor_exists,
    validate_news_monitor_owner,
    validate_news_task_access,
)
from src.news_media.models import NewsMonitor, NewsTask
from src.news_media.schemas import (
    NewsArticleRead,
    NewsMonitorCreate,
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
        db, page=page, page_size=page_size, owner_id=current_user.id, search=search,
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
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
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
):
    if task.phase == "collect":
        await service.execute_news_collect(db, task)
    else:
        await service.execute_news_probe(db, task)
    await db.commit()
    return task


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
