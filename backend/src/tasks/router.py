"""
爬虫任务API路由
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.pagination import PaginationParams, get_pagination_params

from . import models, schemas, service
from .dependencies import (
    require_crawler_tasks_delete,
    require_crawler_tasks_execute,
    require_crawler_tasks_read,
    require_crawler_tasks_write,
)
from src.data.notes import service as notes_service
from src.data.notes.schemas import NoteInDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crawler-tasks", tags=["Crawler Tasks"])


# ============================================================================
# 任务管理API
# ============================================================================


@router.post(
    "/",
    response_model=schemas.CrawlerTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建爬虫任务",
)
async def create_task(
    task_data: schemas.CrawlerTaskCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_crawler_tasks_write),
):
    """
    创建新的爬虫任务

    需要权限: crawler_tasks:write
    """
    try:
        task = await service.create_task(db, task_data, current_user.id)
        return schemas.CrawlerTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/",
    response_model=schemas.CrawlerTaskListResponse,
    summary="获取任务列表",
)
async def list_tasks(
    platform: Optional[models.PlatformType] = Query(None, description="按平台筛选"),
    status: Optional[models.TaskStatus] = Query(None, description="按状态筛选"),
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_read),
):
    """
    获取爬虫任务列表(分页)

    需要权限: crawler_tasks:read
    """
    tasks, total = await service.list_tasks(
        db, pagination, platform=platform, status=status
    )

    return schemas.CrawlerTaskListResponse.create(
        items=[schemas.CrawlerTaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{task_id}", response_model=schemas.CrawlerTaskDetail, summary="获取任务详情"
)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_read),
):
    """
    获取任务详情(含日志)

    需要权限: crawler_tasks:read
    """
    task = await service.get_task_with_logs(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return schemas.CrawlerTaskDetail.model_validate(task)


@router.patch(
    "/{task_id}", response_model=schemas.CrawlerTaskResponse, summary="更新任务"
)
async def update_task(
    task_id: int,
    update_data: schemas.CrawlerTaskUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_write),
):
    """
    更新任务配置

    需要权限: crawler_tasks:write
    """
    task = await service.update_task(db, task_id, update_data)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return schemas.CrawlerTaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除任务")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_delete),
):
    """
    删除任务(仅限未运行的任务)

    需要权限: crawler_tasks:delete
    """
    try:
        success = await service.delete_task(db, task_id)
        if not success:
            raise HTTPException(status_code=404, detail="任务不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# 任务控制API
# ============================================================================


@router.post(
    "/{task_id}/start", response_model=schemas.CrawlerTaskResponse, summary="启动任务"
)
async def start_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_execute),
):
    """
    启动爬虫任务

    需要权限: crawler_tasks:execute
    """
    try:
        task = await service.start_task(db, task_id)
        return schemas.CrawlerTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{task_id}/pause", response_model=schemas.CrawlerTaskResponse, summary="暂停任务"
)
async def pause_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_execute),
):
    """
    暂停正在运行的任务

    需要权限: crawler_tasks:execute
    """
    try:
        task = await service.pause_task(db, task_id)
        return schemas.CrawlerTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{task_id}/stop", response_model=schemas.CrawlerTaskResponse, summary="停止任务"
)
async def stop_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_execute),
):
    """
    停止任务(不可恢复)

    需要权限: crawler_tasks:execute
    """
    try:
        task = await service.stop_task(db, task_id)
        return schemas.CrawlerTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{task_id}/results",
    response_model=list[NoteInDB],
    summary="获取任务结果",
)
async def list_task_results(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_read),
):
    notes = await notes_service.get_notes_by_task(db, task_id)
    return [NoteInDB.model_validate(note) for note in notes]


# ============================================================================
# 任务日志API
# ============================================================================


@router.get(
    "/{task_id}/logs",
    response_model=list[schemas.TaskLogResponse],
    summary="获取任务日志",
)
async def get_task_logs(
    task_id: int,
    limit: int = Query(100, ge=1, le=1000, description="日志数量限制"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_read),
):
    """
    获取任务执行日志

    需要权限: crawler_tasks:read
    """
    logs = await service.get_task_logs(db, task_id, limit)
    return [schemas.TaskLogResponse.model_validate(log) for log in logs]


# ============================================================================
# 统计API
# ============================================================================


@router.get(
    "/statistics",
    response_model=schemas.TaskStatistics,
    summary="获取任务统计",
)
async def get_statistics(
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_crawler_tasks_read),
):
    """
    获取任务统计信息

    需要权限: crawler_tasks:read
    """
    return await service.get_task_statistics(db)
