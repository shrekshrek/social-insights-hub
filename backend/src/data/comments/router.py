"""Comment data API routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.tasks.models import PlatformType

from . import schemas, service
from .dependencies import require_comments_read, require_comments_write

router = APIRouter(prefix="/data/comments", tags=["Comments Data"])


@router.get(
    "",
    response_model=List[schemas.CommentInDB],
    summary="评论数据列表",
)
async def list_comments(
    platform: str | None = Query(None, description="平台过滤"),
    note_id: str | None = Query(None, description="笔记ID过滤"),
    author_id: str | None = Query(None, description="作者ID过滤"),
    parent_comment_id: str | None = Query(None, description="父评论ID过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """获取评论数据列表，支持平台、笔记、作者和父评论过滤。"""
    platform_enum = None
    if platform:
        try:
            platform_enum = PlatformType(platform)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="无效的平台标识") from exc

    comments = await service.list_comments(
        db, platform_enum, note_id, author_id, parent_comment_id, skip, limit
    )
    return [schemas.CommentInDB.model_validate(comment) for comment in comments]


@router.get(
    "/{comment_id}",
    response_model=schemas.CommentInDB,
    summary="评论数据详情",
)
async def get_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """根据数据库ID获取评论详情。"""
    comment = await service.get_comment(db, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    return schemas.CommentInDB.model_validate(comment)


@router.get(
    "/by-platform/{platform}/{platform_comment_id}",
    response_model=schemas.CommentInDB,
    summary="通过平台ID获取评论",
)
async def get_comment_by_platform_id(
    platform: str,
    platform_comment_id: str,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """根据平台和平台评论ID获取评论。"""
    try:
        platform_enum = PlatformType(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的平台标识") from exc

    comment = await service.get_comment_by_platform_id(
        db, platform_enum.value, platform_comment_id
    )
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    return schemas.CommentInDB.model_validate(comment)


@router.post(
    "",
    response_model=schemas.CommentInDB,
    status_code=status.HTTP_201_CREATED,
    summary="创建评论数据",
)
async def create_comment(
    data: schemas.CommentCreate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_write),
):
    """手动创建评论数据（通常由爬虫任务自动调用）。"""
    comment, created = await service.get_or_create_comment(db, data)
    return schemas.CommentInDB.model_validate(comment)


@router.get(
    "/tasks/{task_id}/comments",
    response_model=List[schemas.CommentInDB],
    summary="获取任务关联的评论",
)
async def get_comments_by_task(
    task_id: int,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """获取指定任务爬取的所有评论。"""
    comments = await service.get_comments_by_task(db, task_id, skip, limit)
    return [schemas.CommentInDB.model_validate(comment) for comment in comments]


@router.get(
    "/{comment_id}/tasks",
    response_model=List[schemas.TaskCommentResponse],
    summary="获取评论关联的任务",
)
async def get_tasks_by_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """获取爬取该评论的所有任务记录。"""
    task_comments = await service.get_tasks_by_comment(db, comment_id)
    return [schemas.TaskCommentResponse.model_validate(tc) for tc in task_comments]


@router.get(
    "/tasks/{task_id}/count",
    response_model=dict,
    summary="统计任务评论数",
)
async def count_comments_by_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_comments_read),
):
    """统计指定任务爬取的评论总数。"""
    count = await service.count_comments_by_task(db, task_id)
    return {"task_id": task_id, "comment_count": count}
