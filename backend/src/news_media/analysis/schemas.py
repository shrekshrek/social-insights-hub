"""新闻分析切片 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class NewsSliceCreate(CustomBaseModel):
    """创建新闻切片"""

    name: str = Field(..., min_length=1, max_length=255)
    included_task_ids: list[int] = Field(..., min_length=1)
    subject: str | None = Field(
        default=None,
        max_length=255,
        description="聚焦切片的主体品牌名（None=大盘视角，无 target/competitor 区分）",
    )
    competitors: list[str] = Field(
        default_factory=list,
        description="聚焦切片的竞品品牌名列表（subject 为 None 时应为空）",
    )


class NewsSliceRead(CustomBaseModel):
    """新闻切片详情。

    subject / competitors 是切片配置（表列），与分析产物 result_data 解耦。
    """

    id: int
    name: str
    monitor_id: int
    included_task_ids: list[int]
    subject: str | None
    competitors: list[str]
    status: str
    result_data: dict | None
    stats: dict | None
    error_message: str | None
    user_id: int
    created_at: datetime
    updated_at: datetime


class NewsSliceReadWithRelations(NewsSliceRead):
    """新闻切片详情（含关联信息）"""

    monitor_name: str | None = None
    user_username: str | None = None

    @classmethod
    def from_orm_full(cls, slice_obj) -> "NewsSliceReadWithRelations":
        return cls(
            id=slice_obj.id,
            name=slice_obj.name,
            monitor_id=slice_obj.monitor_id,
            included_task_ids=slice_obj.included_task_ids,
            subject=slice_obj.subject,
            competitors=list(slice_obj.competitors or []),
            status=slice_obj.status,
            result_data=slice_obj.result_data,
            stats=slice_obj.stats,
            error_message=slice_obj.error_message,
            user_id=slice_obj.user_id,
            created_at=slice_obj.created_at,
            updated_at=slice_obj.updated_at,
            monitor_name=slice_obj.monitor.name if slice_obj.monitor else None,
            user_username=slice_obj.user.username if slice_obj.user else None,
        )
