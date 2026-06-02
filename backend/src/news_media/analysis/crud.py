"""新闻切片 CRUD

切片创建走 `service.initialize_slice`（同步落 stage1：meta + descriptive），
此处仅提供查询 / 删除。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.news_media.analysis.models import NewsSlice


async def get_news_slice(db: AsyncSession, slice_id: int) -> NewsSlice | None:
    return await db.get(NewsSlice, slice_id)


async def get_slices_by_monitor(db: AsyncSession, monitor_id: int) -> list[NewsSlice]:
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
