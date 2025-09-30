from typing import Any, List
from pydantic import Field
from fastapi import Query
from src.schemas import CustomBaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PaginationParams(CustomBaseModel):
    """分页参数"""

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页大小")

    @property
    def offset(self) -> int:
        """计算偏移量"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """获取限制数量"""
        return self.page_size


def get_pagination_params(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
) -> PaginationParams:
    """分页参数依赖注入"""
    return PaginationParams(page=page, page_size=page_size)


async def paginate_query(
    db: AsyncSession, query, pagination: PaginationParams
) -> tuple[List[Any], int]:
    """
    对查询进行分页

    Args:
        db: 数据库会话
        query: SQLAlchemy查询对象
        pagination: 分页参数

    Returns:
        tuple: (items, total_count)
    """
    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 获取分页数据
    paginated_query = query.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(paginated_query)
    items = result.scalars().all()

    return items, total
