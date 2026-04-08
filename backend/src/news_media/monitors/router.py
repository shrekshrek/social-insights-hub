"""新闻监测项目 API 路由"""

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.news_media.monitors import service
from src.news_media.monitors.dependencies import (
    validate_news_monitor_access,
    validate_news_monitor_exists,
    validate_news_monitor_owner,
)
from src.news_media.monitors.models import NewsMonitor
from src.news_media.monitors.schemas import (
    NewsMonitorCreate,
    NewsMonitorParticipantAssignment,
    NewsMonitorRead,
    NewsMonitorReadWithOwner,
    NewsMonitorUpdate,
)
from src.schemas import MessageResponse, PaginatedResponse

router = APIRouter(prefix="/news-media", tags=["News Media - Monitors"])


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
