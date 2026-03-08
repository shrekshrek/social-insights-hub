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
    slice_plan: list[dict[str, Any]] | None = Field(
        None, description="用户确认（可修改）后的切片规划"
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

    understanding_summary: str = Field("", description="AI 对分析需求的一句话理解")
    monitor_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    slice_plan: list[dict[str, Any]] = Field(default_factory=list)


class ConfirmPlanResponse(CustomBaseModel):
    """确认计划响应"""

    created_monitor_ids: list[int]
    partial_errors: list[str] = Field(default_factory=list)
    strategy: StrategyRead


class StructureAnalysisResult(CustomBaseModel):
    """切片结构优化分析结果（Architect Chain 输出）"""

    summary: str = ""
    current_slice_issues: list[dict[str, Any]] = Field(default_factory=list)
    unused_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    recommended_structure: list[dict[str, Any]] = Field(default_factory=list)
    collection_still_needed: bool = False
    collection_note: str | None = None


class EvaluationResultResponse(CustomBaseModel):
    """充分性评估响应（含结构优化分析）"""

    overall_score: float
    is_sufficient: bool
    coverage_analysis: list[dict[str, Any]] = Field(default_factory=list)
    slice_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    gap_analysis: list[dict[str, Any]] = Field(default_factory=list)
    supplementary_suggestions: list[dict[str, Any]] | None = None
    supplementary_slice_plan: list[dict[str, Any]] | None = None
    pending_supplementary_task_ids: list[int] | None = None
    structure_analysis: StructureAnalysisResult | None = None


class ConfirmSupplementaryRequest(CustomBaseModel):
    """确认补充采集请求"""

    monitor_suggestions: list[dict[str, Any]] = Field(
        ..., min_length=1, description="补充采集建议列表"
    )
    notes_per_task: int = Field(
        50, ge=50, le=100, description="每个任务的采集数量（50 或 100）"
    )


class ConfirmSupplementaryResponse(CustomBaseModel):
    """确认补充采集响应"""

    created_task_ids: list[int]
    task_count: int
    partial_errors: list[str] = Field(default_factory=list)
    strategy: StrategyRead


class SupplementaryStatusResponse(CustomBaseModel):
    """补充采集状态"""

    total: int
    completed: int
    pending: int
    all_done: bool
    completed_task_ids: list[int] = Field(default_factory=list)


StrategyListResponse = PaginatedResponse[StrategyListItem]


# ==================== Brief 文档解析 ====================


class ParseBriefResponse(CustomBaseModel):
    """从上传文档解析出的 Brief 预填字段"""

    strategy_name: str = Field("", description="建议策略名称")
    brand_name: str = Field("", description="品牌/产品名")
    analysis_goal: str = Field("", description="分析目标")
    constraints: str = Field("", description="补充说明")
