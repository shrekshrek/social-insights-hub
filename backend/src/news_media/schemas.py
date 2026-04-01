"""新闻媒体模块 Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class NewsMonitorCreate(CustomBaseModel):
    """创建新闻监测项目"""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    search_provider: str = Field(default="serpapi_baidu")


class NewsMonitorRead(CustomBaseModel):
    """新闻监测项目详情"""

    id: int
    name: str
    description: str | None
    owner_id: int
    search_provider: str
    created_at: datetime
    updated_at: datetime


class NewsTaskCreate(CustomBaseModel):
    """创建新闻任务"""

    name: str = Field(..., min_length=1, max_length=255)
    keywords: str = Field(..., min_length=1)
    search_params: dict | None = None


class NewsTaskRead(CustomBaseModel):
    """新闻任务详情"""

    id: int
    name: str
    monitor_id: int
    strategy_id: int | None
    keywords: str
    phase: str | None
    status: str
    search_provider: str
    search_params: dict | None
    articles_count: int
    analysis_result: dict | None
    error_message: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime
