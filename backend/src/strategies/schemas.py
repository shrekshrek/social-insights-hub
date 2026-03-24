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


# ==================== 研究设计 Schemas ====================


class DesignResearchRequest(CustomBaseModel):
    """AI 研究设计请求"""

    user_input: str = Field("", description="用户补充说明（可为空，AI 将基于 Brief 直接设计）")


class DesignResearchResponse(CustomBaseModel):
    """AI 研究设计响应"""

    understanding_summary: str = Field("", description="AI 对分析需求的理解")
    research_questions: list[dict[str, Any]] = Field(default_factory=list)
    data_plan: list[dict[str, Any]] = Field(default_factory=list)
    slice_blueprint: list[dict[str, Any]] = Field(default_factory=list)
    output_type: str = Field("brand_strategy")
    output_type_rationale: str = Field("")


class ConfirmResearchRequest(CustomBaseModel):
    """确认研究计划，创建 Monitor + 探测任务"""

    research_design: dict[str, Any] = Field(
        ..., description="用户编辑后的研究计划（完整 JSON）"
    )
    notes_per_task: int = Field(
        50, ge=10, le=100, description="每个任务的全量采集数量"
    )
    probe_notes: int = Field(
        15, ge=5, le=30, description="每个任务的探测采集数量"
    )


class ConfirmResearchResponse(CustomBaseModel):
    """确认研究计划响应"""

    created_monitor_id: int
    created_task_count: int
    partial_errors: list[str] = Field(default_factory=list)
    strategy: "StrategyRead"


# ==================== 探测验证 Schemas ====================


class ProbeTaskStatus(CustomBaseModel):
    """单个探测任务状态"""

    task_id: int
    keyword: str = ""
    platform: str = ""
    status: str = Field(..., description="任务状态")
    has_analysis: bool = Field(False, description="是否已有分析结果")


class ProbeStatusResponse(CustomBaseModel):
    """探测进度响应"""

    all_analyzed: bool = Field(False, description="所有探测任务是否都已完成分析")
    tasks: list[ProbeTaskStatus] = Field(default_factory=list)
    analyzed_count: int = 0
    total_count: int = 0
    probe_review_result: dict | None = Field(None, description="审查结果（全部分析完成后自动填充）")
    strategy: "StrategyRead | None" = None


class ApproveProbeResponse(CustomBaseModel):
    """手动确认探测通过响应"""

    approved_task_count: int
    strategy: "StrategyRead"


class RefinementItem(CustomBaseModel):
    """关键词调整项"""

    task_id: int = Field(..., description="要替换的旧任务 ID")
    new_keyword: str = Field(..., min_length=1, description="新关键词")
    platform: str = Field(..., description="平台代码")


class RefineProbeRequest(CustomBaseModel):
    """调整关键词请求"""

    refinements: list[RefinementItem] = Field(
        ..., min_length=1, description="关键词调整列表"
    )


class RefineProbeResponse(CustomBaseModel):
    """调整关键词响应"""

    removed_task_ids: list[int] = Field(default_factory=list)
    created_task_ids: list[int] = Field(default_factory=list)
    probe_round: int
    strategy: "StrategyRead"


# ==================== 数据就绪 Schemas ====================


class CollectionTaskStatus(CustomBaseModel):
    """单个采集任务状态"""

    task_id: int
    status: str
    has_analysis: bool = False


class CollectionStatusResponse(CustomBaseModel):
    """全量采集进度响应"""

    all_completed: bool = False
    all_analyzed: bool = False
    slices_created: bool = False
    tasks: list[CollectionTaskStatus] = Field(default_factory=list)
    completed_count: int = 0
    total_count: int = 0
    coverage_check_result: dict | None = None
    strategy: "StrategyRead | None" = None


class DataOverviewResponse(CustomBaseModel):
    """数据全景响应"""

    slices: list["SliceSummary"] = Field(default_factory=list)
    coverage_check_result: dict | None = None
    strategy: "StrategyRead"


class AdjustSliceItem(CustomBaseModel):
    """切片调整项"""

    slice_id: int = Field(..., description="要调整的切片 ID")
    name: str | None = Field(None, description="新名称")
    subject: str | None = Field(None, description="新主体品牌")
    competitors: list[str] | None = Field(None, description="新竞品列表")


class AdjustSlicesRequest(CustomBaseModel):
    """切片微调请求"""

    adjustments: list[AdjustSliceItem] = Field(
        ..., min_length=1, description="切片调整列表"
    )


# ==================== 旧 Schemas（待 Step 7 移除）====================


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

    # ① 研究设计
    research_design: dict | None = None

    # ② 探测验证
    probe_review_result: dict | None = None
    probe_round: int = 0

    # ③ 数据就绪
    coverage_check_result: dict | None = None

    # ④ 产出生成
    output_type: str | None = None
    phase1_result: dict | None = None
    phase2_result: dict | None = None
    phase3_result: dict | None = None

    # 关联
    monitor_id: int | None = None
    task_ids: list[int] = Field(default_factory=list)
    slices: list[SliceSummary] = Field(default_factory=list)

    # 元信息
    created_by: int
    creator_name: str
    created_at: datetime
    updated_at: datetime


StrategyListResponse = PaginatedResponse[StrategyListItem]


# ==================== Brief 文档解析 ====================


class ParseBriefResponse(CustomBaseModel):
    """从上传文档解析出的 Brief 预填字段"""

    strategy_name: str = Field("", description="建议策略名称")
    brand_name: str = Field("", description="品牌/产品名")
    analysis_goal: str = Field("", description="分析目标")
    constraints: str = Field("", description="补充说明")
