"""Analysis CRUD helpers（轻量数据库查询，不含业务逻辑）"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AnalysisSlice


async def check_slice_exists(db: AsyncSession, monitor_id: int) -> bool:
    """检查指定 monitor 下是否已存在至少一个分析切片。

    用于 check_collection_status 中判断是否需要触发自动建切片。
    """
    stmt = select(func.count()).where(AnalysisSlice.monitor_id == monitor_id)
    result = await db.execute(stmt)
    count = result.scalar_one()
    return count > 0
