"""Note data API routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.tasks.models import PlatformType

from . import schemas, service
from .dependencies import require_notes_read, require_notes_write

router = APIRouter(prefix="/data/notes", tags=["Notes Data"])


@router.get(
    "",
    response_model=List[schemas.NoteInDB],
    summary="笔记数据列表",
)
async def list_notes(
    platform: str | None = Query(None, description="平台过滤"),
    author_id: str | None = Query(None, description="作者ID过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """获取笔记数据列表，支持平台和作者过滤。"""
    platform_enum = None
    if platform:
        try:
            platform_enum = PlatformType(platform)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="无效的平台标识") from exc

    notes = await service.list_notes(db, platform_enum, author_id, skip, limit)
    return [schemas.NoteInDB.model_validate(note) for note in notes]


@router.get(
    "/{note_id}",
    response_model=schemas.NoteInDB,
    summary="笔记数据详情",
)
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """根据数据库ID获取笔记详情。"""
    note = await service.get_note(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return schemas.NoteInDB.model_validate(note)


@router.get(
    "/by-platform/{platform}/{platform_note_id}",
    response_model=schemas.NoteInDB,
    summary="通过平台ID获取笔记",
)
async def get_note_by_platform_id(
    platform: str,
    platform_note_id: str,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """根据平台和平台笔记ID获取笔记。"""
    try:
        platform_enum = PlatformType(platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的平台标识") from exc

    note = await service.get_note_by_platform_id(
        db, platform_enum.value, platform_note_id
    )
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return schemas.NoteInDB.model_validate(note)


@router.post(
    "",
    response_model=schemas.NoteInDB,
    status_code=status.HTTP_201_CREATED,
    summary="创建笔记数据",
)
async def create_note(
    data: schemas.NoteCreate,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_write),
):
    """手动创建笔记数据（通常由爬虫任务自动调用）。"""
    note, created = await service.get_or_create_note(db, data)
    return schemas.NoteInDB.model_validate(note)


@router.get(
    "/tasks/{task_id}/notes",
    response_model=List[schemas.NoteInDB],
    summary="获取任务关联的笔记",
)
async def get_notes_by_task(
    task_id: int,
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """获取指定任务爬取的所有笔记。"""
    notes = await service.get_notes_by_task(db, task_id, skip, limit)
    return [schemas.NoteInDB.model_validate(note) for note in notes]


@router.get(
    "/{note_id}/tasks",
    response_model=List[schemas.TaskNoteResponse],
    summary="获取笔记关联的任务",
)
async def get_tasks_by_note(
    note_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """获取爬取该笔记的所有任务记录。"""
    task_notes = await service.get_tasks_by_note(db, note_id)
    return [schemas.TaskNoteResponse.model_validate(tn) for tn in task_notes]


@router.get(
    "/tasks/{task_id}/count",
    response_model=dict,
    summary="统计任务笔记数",
)
async def count_notes_by_task(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_notes_read),
):
    """统计指定任务爬取的笔记总数。"""
    count = await service.count_notes_by_task(db, task_id)
    return {"task_id": task_id, "note_count": count}
