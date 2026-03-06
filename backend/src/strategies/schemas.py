"""策略定义 Pydantic Schemas"""

from datetime import datetime
from typing import Any

from pydantic import Field

from src.schemas import CustomBaseModel, PaginatedResponse


# ==================== Brand Brief ====================


class BrandBrief(CustomBaseModel):
    """结构化品牌简报"""

    brand_name: str = Field(..., min_length=1, description="品牌/产品名")
    analysis_goal: str = Field(..., min_length=1, description="分析目标")
    industry: str | None = Field(None, description="行业")
    competitors: list[str] = Field(default_factory=list, description="关注的竞品")
    focus_areas: list[str] = Field(default_factory=list, description="关注维度")
    time_range: str | None = Field(None, description="期望数据时间范围")
    constraints: str | None = Field(None, description="其他约束/备注")


# ==================== Request Schemas ====================


class StrategyCreate(CustomBaseModel):
    """创建策略请求"""

    name: str = Field(..., min_length=1, max_length=255, description="策略名称")
    slice_ids: list[int] = Field(default_factory=list, description="关联切片ID列表（可选）")
    brand_brief: BrandBrief | None = Field(None, description="结构化 Brand Brief（可选）")


class StrategyUpdate(CustomBaseModel):
    """更新策略请求"""

    name: str | None = Field(None, min_length=1, max_length=255, description="策略名称")
    brand_brief: BrandBrief | None = None


class PhaseResultEdit(CustomBaseModel):
    """编辑阶段结果请求"""

    result: dict = Field(..., description="阶段结果 JSON")


# ==================== 新增请求 Schemas ====================


class ConsultRequest(CustomBaseModel):
    """AI 监测方案生成请求"""

    user_input: str = Field("", description="用户补充说明（可为空，AI 将基于 Brand Brief 直接规划）")


class ConfirmPlanRequest(CustomBaseModel):
    """确认 AI 建议并一键创建监测"""

    monitor_suggestions: list[dict[str, Any]] = Field(
        ..., min_length=1, description="用户确认（可修改）后的监测建议列表"
    )
    notes_per_task: int = Field(
        50, ge=50, le=100, description="每个任务的采集数量（50 或 100）"
    )


class AddSlicesRequest(CustomBaseModel):
    """批量关联切片"""

    slice_ids: list[int] = Field(..., min_length=1, description="切片ID列表")


# ==================== Response Schemas ====================


class SliceSummary(CustomBaseModel):
    """切片摘要"""

    slice_id: int
    slice_name: str | None = None
    monitor_id: int
    monitor_name: str


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
    """策略详情"""

    id: int
    name: str
    status: str
    brand_brief: BrandBrief | None = None
    consultation_rounds: list[dict] = Field(default_factory=list)
    suggested_monitor_ids: list[int] = Field(default_factory=list)
    slice_plan: list[dict] = Field(default_factory=list)
    evaluation_result: dict | None = None
    phase1_result: dict | None = None
    phase2_result: dict | None = None
    phase3_result: dict | None = None
    slices: list[SliceSummary] = Field(default_factory=list)
    created_by: int
    creator_name: str
    created_at: datetime
    updated_at: datetime


# ==================== 新增响应 Schemas ====================


class ConsultResponse(CustomBaseModel):
    """AI 监测方案响应"""

    monitor_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    slice_plan: list[dict[str, Any]] = Field(default_factory=list)


class ConfirmPlanResponse(CustomBaseModel):
    """确认计划响应"""

    created_monitor_ids: list[int]
    partial_errors: list[str] = Field(default_factory=list)
    strategy: StrategyRead


class EvaluationResultResponse(CustomBaseModel):
    """充分性评估响应"""

    overall_score: float
    is_sufficient: bool
    coverage_analysis: list[dict[str, Any]] = Field(default_factory=list)
    slice_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    gap_analysis: list[dict[str, Any]] = Field(default_factory=list)
    supplementary_tasks: list[dict[str, Any]] | None = None


StrategyListResponse = PaginatedResponse[StrategyListItem]
