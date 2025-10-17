"""
爬虫任务 Pydantic 模型
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import Field, field_validator

from src.schemas import CustomBaseModel, PaginatedResponse

from .models import CrawlerType, PlatformType, TaskStatus


# ============================================================================
# 任务配置相关
# ============================================================================


class TaskConfig(CustomBaseModel):
    """任务配置基础模型"""

    keywords: Optional[str] = Field(None, description="关键词(多个用逗号分隔)")
    urls: Optional[list[str]] = Field(None, description="指定URL列表")
    max_count: int = Field(40, ge=1, le=1000, description="最大爬取数量")
    enable_comments: bool = Field(True, description="是否爬取评论")
    enable_sub_comments: bool = Field(False, description="是否爬取二级评论")
    max_comments_per_item: int = Field(
        0, ge=0, description="单条内容最大评论数(0=不限)"
    )
    sort_type: Optional[str] = Field(None, description="排序方式")
    account_ids: Optional[list[int]] = Field(None, description="指定账号ID列表")
    proxy_enabled: bool = Field(True, description="是否使用代理")
    enable_checkpoint: bool = Field(True, description="是否启用断点续爬")

    model_config = {"extra": "allow"}  # 允许额外字段


# ============================================================================
# 任务创建/更新
# ============================================================================


class CrawlerTaskCreate(CustomBaseModel):
    """创建爬虫任务"""

    name: str = Field(..., min_length=1, max_length=255, description="任务名称")
    platform: PlatformType = Field(..., description="爬取平台")
    crawler_type: CrawlerType = Field(..., description="爬取模式")
    config: dict[str, Any] = Field(..., description="爬取配置")

    model_config = {"use_enum_values": True}

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict, info) -> dict:
        """验证配置有效性"""
        # 根据 crawler_type 验证必需字段
        if "crawler_type" in info.data:
            crawler_type = info.data["crawler_type"]
            if crawler_type == CrawlerType.SEARCH and not v.get("keywords"):
                raise ValueError("搜索模式必须提供 keywords")
            if crawler_type in [CrawlerType.DETAIL, CrawlerType.CREATOR] and not v.get(
                "urls"
            ):
                raise ValueError(f"{crawler_type} 模式必须提供 urls")
        return v


class CrawlerTaskUpdate(CustomBaseModel):
    """更新爬虫任务"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    config: Optional[dict[str, Any]] = None
    status: Optional[TaskStatus] = None


# ============================================================================
# 任务响应
# ============================================================================


class CrawlerTaskResponse(CustomBaseModel):
    """爬虫任务响应"""

    id: int
    name: str
    platform: PlatformType
    crawler_type: CrawlerType
    status: TaskStatus
    config: dict[str, Any]
    progress: int
    crawled_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    checkpoint_id: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrawlerTaskDetail(CrawlerTaskResponse):
    """爬虫任务详情(含日志)"""

    logs: list["TaskLogResponse"] = []


# ============================================================================
# 任务日志
# ============================================================================


class TaskLogCreate(CustomBaseModel):
    """创建任务日志"""

    task_id: int
    level: str = Field(..., pattern="^(INFO|WARNING|ERROR)$")
    message: str
    detail: Optional[dict[str, Any]] = None


class TaskLogResponse(CustomBaseModel):
    """任务日志响应"""

    id: int
    task_id: int
    level: str
    message: str
    detail: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================================
# 任务统计
# ============================================================================


class TaskStatistics(CustomBaseModel):
    """任务统计"""

    total: int = 0
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0


# ============================================================================
# 分页响应类型别名
# ============================================================================

CrawlerTaskListResponse = PaginatedResponse[CrawlerTaskResponse]
TaskLogListResponse = PaginatedResponse[TaskLogResponse]
