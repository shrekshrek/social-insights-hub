"""新闻监测项目服务层"""

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.monitors import crud
from src.news_media.monitors.models import NewsMonitor
from src.news_media.monitors.schemas import NewsMonitorCreate, NewsMonitorUpdate

logger = logging.getLogger(__name__)


async def create_news_monitor(
    db: AsyncSession, data: NewsMonitorCreate, user_id: int
) -> NewsMonitor:
    """创建新闻监测项目"""
    existing = await crud.get_monitor_by_name(db, data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"监测项目名称 '{data.name}' 已存在",
        )
    monitor_data = data.model_dump(exclude={"participant_ids"})
    monitor = await crud.create_monitor(db, monitor_data, user_id, participant_ids=data.participant_ids)
    await db.commit()
    await db.refresh(monitor, ["owner", "participants"])
    return monitor


async def get_news_monitors(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    participant_id: int | None = None,
    search: str | None = None,
) -> tuple[list[NewsMonitor], int]:
    """获取新闻监测项目列表"""
    skip = (page - 1) * page_size
    return await crud.get_monitors(
        db, skip=skip, limit=page_size,
        user_id=user_id, participant_id=participant_id, search=search,
    )


async def get_news_monitor(db: AsyncSession, monitor_id: int) -> NewsMonitor | None:
    """获取单个新闻监测项目"""
    return await crud.get_monitor_by_id(db, monitor_id, load_relations=True)


async def update_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, data: NewsMonitorUpdate
) -> NewsMonitor:
    """更新新闻监测项目"""
    update_data = data.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != monitor.name:
        existing = await crud.get_monitor_by_name(db, update_data["name"])
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"监测项目名称 '{update_data['name']}' 已存在",
            )
    monitor = await crud.update_monitor(db, monitor, update_data)
    await db.commit()
    await db.refresh(monitor, ["owner", "participants"])
    return monitor


async def delete_news_monitor(db: AsyncSession, monitor: NewsMonitor) -> None:
    """删除新闻监测项目"""
    await crud.delete_monitor(db, monitor)
    await db.commit()


async def add_participants_to_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_ids: list[int]
) -> NewsMonitor:
    """为新闻监测项目添加参与者（owner 不会被加入）"""
    if monitor.user_id in user_ids:
        user_ids = [uid for uid in user_ids if uid != monitor.user_id]
    if not user_ids:
        return monitor
    return await crud.add_participants_to_news_monitor(db, monitor, user_ids)


async def remove_participant_from_news_monitor(
    db: AsyncSession, monitor: NewsMonitor, user_id: int
) -> NewsMonitor:
    """从新闻监测项目移除参与者"""
    if user_id == monitor.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除项目所有者",
        )
    if user_id not in {p.id for p in monitor.participants}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 {user_id} 不是该项目的参与者",
        )
    return await crud.remove_participant_from_news_monitor(db, monitor, user_id)


