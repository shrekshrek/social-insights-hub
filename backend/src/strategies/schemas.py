"""策略定义 Pydantic Schemas"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel, PaginatedResponse


# ==================== Request Schemas ====================


class StrategyCreate(CustomBaseModel):
    """创建策略请求"""

    name: str = Field(..., min_length=1, max_length=255, description="策略名称")
    slice_ids: list[int] = Field(..., min_length=1, description="关联切片ID列表")
    brand_brief: dict | None = Field(None, description="可选 Brand Brief")


class StrategyUpdate(CustomBaseModel):
    """更新策略请求"""

    name: str | None = Field(None, min_length=1, max_length=255, description="策略名称")
    brand_brief: dict | None = None


class PhaseResultEdit(CustomBaseModel):
    """编辑阶段结果请求"""

    result: dict = Field(..., description="阶段结果 JSON")


# ==================== Response Schemas ====================


class SliceSummary(CustomBaseModel):
    """切片摘要"""

    slice_id: int
    slice_name: str | None = None
    project_id: int
    project_name: str


class StrategyListItem(CustomBaseModel):
    """策略列表项"""

    id: int
    name: str
    status: str
    slice_count: int
    created_by: int
    creator_name: str
    created_at: datetime
    updated_at: datetime


class StrategyRead(CustomBaseModel):
    """策略��情"""

    id: int
    name: str
    status: str
    brand_brief: dict | None = None
    phase1_result: dict | None = None
    phase2_result: dict | None = None
    phase3_result: dict | None = None
    slices: list[SliceSummary] = Field(default_factory=list)
    created_by: int
    creator_name: str
    created_at: datetime
    updated_at: datetime


StrategyListResponse = PaginatedResponse[StrategyListItem]
