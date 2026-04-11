"""新闻切片 CRUD"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.analysis.models import NewsSlice


async def create_news_slice(
    db: AsyncSession,
    monitor_id: int,
    name: str,
    included_task_ids: list[int],
    user_id: int,
) -> NewsSlice:
    slice_obj = NewsSlice(
        name=name,
        monitor_id=monitor_id,
        included_task_ids=included_task_ids,
        user_id=user_id,
    )
    db.add(slice_obj)
    await db.commit()
    await db.refresh(slice_obj)
    return slice_obj


async def get_news_slice(
    db: AsyncSession, slice_id: int
) -> NewsSlice | None:
    return await db.get(NewsSlice, slice_id)


async def get_slices_by_monitor(
    db: AsyncSession, monitor_id: int
) -> list[NewsSlice]:
    stmt = (
        select(NewsSlice)
        .where(NewsSlice.monitor_id == monitor_id)
        .order_by(NewsSlice.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_news_slice(db: AsyncSession, slice_obj: NewsSlice) -> None:
    await db.delete(slice_obj)
    await db.commit()
