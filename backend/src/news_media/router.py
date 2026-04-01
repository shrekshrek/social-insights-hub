"""新闻媒体 API 路由"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_db
from src.news_media import service
from src.news_media.schemas import (
    NewsMonitorCreate,
    NewsMonitorRead,
    NewsTaskCreate,
    NewsTaskRead,
)

router = APIRouter(prefix="/news-media", tags=["News Media"])


@router.post(
    "/monitors",
    response_model=NewsMonitorRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新闻监测项目",
)
async def create_monitor(
    data: NewsMonitorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新闻监测项目"""
    monitor = await service.create_news_monitor(db, data, current_user.id)
    await db.commit()
    return monitor


@router.post(
    "/monitors/{monitor_id}/tasks",
    response_model=NewsTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建并执行新闻任务",
)
async def create_and_execute_task(
    monitor_id: int,
    data: NewsTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新闻任务并立即执行"""
    task = await service.create_news_task(db, monitor_id, data, current_user.id)
    await db.commit()

    # 立即执行探测
    await service.execute_news_probe(db, task)
    await db.commit()

    return task
