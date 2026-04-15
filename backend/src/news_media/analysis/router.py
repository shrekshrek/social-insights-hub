"""新闻切片 API 端点

子资源风格：/news-media/monitors/{monitor_id}/slices
"""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.rbac.dependencies import (
    require_news_monitor_read,
    require_news_monitor_write,
    require_news_monitor_delete,
)
from src.news_media.analysis import crud, service
from src.news_media.analysis.schemas import (
    NewsSliceCreate,
    NewsSliceRead,
    NewsSliceReadWithRelations,
)
from src.news_media.monitors.dependencies import validate_news_monitor_exists
from src.news_media.monitors.models import NewsMonitor

router = APIRouter(prefix="/news-media", tags=["News Media - Analysis"])


@router.get(
    "/monitors/{monitor_id}/slices",
    response_model=list[NewsSliceRead],
    status_code=status.HTTP_200_OK,
    summary="获取监测项目下的切片列表",
)
async def list_slices(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_monitor_read),
):
    return await crud.get_slices_by_monitor(db, monitor.id)


@router.post(
    "/monitors/{monitor_id}/slices",
    response_model=NewsSliceRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新闻切片",
)
async def create_slice(
    data: NewsSliceCreate,
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_news_monitor_write),
):
    return await service.create_slice(db, monitor.id, data, current_user.id)


@router.get(
    "/slices/{slice_id}",
    response_model=NewsSliceReadWithRelations,
    status_code=status.HTTP_200_OK,
    summary="获取切片详情",
)
async def get_slice(
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_monitor_read),
):
    slice_obj = await crud.get_news_slice(db, slice_id)
    if not slice_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="切片不存在",
        )
    return NewsSliceReadWithRelations.from_orm_full(slice_obj)


@router.post(
    "/slices/{slice_id}/analyze",
    response_model=NewsSliceRead,
    status_code=status.HTTP_200_OK,
    summary="运行切片 insight 分析",
)
async def analyze_slice(
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_news_monitor_write),
    analysis_goal: str = Body(default="", embed=True),
    subject: str = Body(default="", embed=True),
):
    slice_obj = await crud.get_news_slice(db, slice_id)
    if not slice_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="切片不存在",
        )
    return await service.run_slice_analysis(
        db, slice_obj, user_id=current_user.id,
        analysis_goal=analysis_goal, subject=subject,
    )


@router.delete(
    "/slices/{slice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除切片",
)
async def delete_slice(
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_monitor_delete),
):
    slice_obj = await crud.get_news_slice(db, slice_id)
    if not slice_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="切片不存在",
        )
    await crud.delete_news_slice(db, slice_obj)
