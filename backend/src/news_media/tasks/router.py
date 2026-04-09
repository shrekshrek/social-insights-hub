"""新闻任务 API 路由"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media.monitors.dependencies import validate_news_monitor_exists
from src.news_media.monitors.models import NewsMonitor
from src.news_media.tasks import service
from src.news_media.tasks.dependencies import validate_news_task_access
from src.news_media.tasks.models import NewsTask
from src.news_media.tasks.schemas import (
    NewsArticleRead,
    NewsTaskCreate,
    NewsTaskRead,
    NewsTaskReadWithRelations,
    NewsTaskRefine,
)
from src.schemas import MessageResponse, PaginatedResponse

router = APIRouter(prefix="/news-media", tags=["News Media - Tasks"])


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
    summary="执行新闻任务（probe 或 collect）",
)
async def execute_task(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """统一的执行入口：根据 task.phase 分发到 probe 或 collect celery。

    - probe：dispatch run_news_probe_task（纯搜索，秒级）
    - collect：dispatch run_news_collect_task（全量流水线）
    """
    from src.news_media.tasks.celery_tasks import (
        run_news_collect_task,
        run_news_probe_task,
    )

    if task.status not in ("pending", "failed"):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务当前状态为 {task.status}，无法执行",
        )

    task.status = "running"
    task.error_message = None
    await db.commit()
    await db.refresh(task)

    if task.phase == "collect":
        from src.analysis.sources.news import create_news_analysis_jobs

        tagging_job_id: int | None = None
        insight_job_id: int | None = None
        if task.auto_analyze:
            tagging_job, insight_job = await create_news_analysis_jobs(
                db=db, task=task, user_id=current_user.id
            )
            tagging_job_id = tagging_job.id
            insight_job_id = insight_job.id
            await db.commit()

        celery_result = run_news_collect_task.delay(
            task_id=task.id,
            tagging_job_id=tagging_job_id,
            insight_job_id=insight_job_id,
        )

        if tagging_job_id is not None:
            from src.analysis.jobs import crud as jobs_crud

            await jobs_crud.set_celery_task_id(db, tagging_job_id, celery_result.id)
            await db.commit()
    else:
        # probe（或 phase 未设时按 probe 处理）
        run_news_probe_task.delay(task_id=task.id)

    return task


@router.post(
    "/tasks/{task_id}/approve",
    response_model=NewsTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="确认 probe 结果并启动 collect 任务",
)
async def approve_probe(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """基于已完成的 probe 任务创建 collect 任务并派发 celery 全量流水线。"""
    collect_task = await service.approve_probe_task(db, task, current_user.id)
    return collect_task


@router.post(
    "/tasks/{task_id}/refine",
    response_model=NewsTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="替换关键词并创建新一轮 probe 任务",
)
async def refine_probe(
    payload: NewsTaskRefine,
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """基于某个 probe 任务创建下一轮 probe（换关键词，probe_round+1）并派发 celery。"""
    new_probe = await service.refine_probe_task(
        db, task, new_keywords=payload.keywords, user_id=current_user.id
    )
    return new_probe


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
    from src.news_media.tasks import crud as tasks_crud

    skip = (page - 1) * page_size
    articles, total = await tasks_crud.get_articles_by_task(
        db, task_id=task.id, skip=skip, limit=page_size,
        relevance=relevance, source_tier=source_tier,
    )
    items = [NewsArticleRead.model_validate(a) for a in articles]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)
