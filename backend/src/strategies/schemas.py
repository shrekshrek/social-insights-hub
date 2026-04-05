"""策略定义 Pydantic Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field, model_validator

from src.schemas import CustomBaseModel, PaginatedResponse

if TYPE_CHECKING:
    from src.strategies.models import Strategy


# ==================== Brand Brief ====================


class ChannelPlanItem(CustomBaseModel):
    """渠道分发条目"""

    type: str = Field(description="渠道类型: social_media / knowledge_base / news_media")
    available: bool = Field(description="当前是否可用")
    solvable: list[str] = Field(default_factory=list, description="该渠道能解决的研究问题")
    unsolvable: list[str] = Field(default_factory=list, description="该渠道的局限")
    channel_brief: str = Field("", description="针对该渠道的定制化研究描述，作为该渠道 research_design 的输入")


class BrandBrief(CustomBaseModel):
    """结构化品牌简报"""

    subject: str = Field(..., min_length=1, description="研究主体（品牌/产品/品类）")
    analysis_goal: str = Field(..., min_length=1, description="分析目标")
    constraints: str | None = Field(None, description="其他约束/备注")
    channel_plan: list[ChannelPlanItem] | None = Field(None, description="渠道分发建议")


# ==================== Request Schemas ====================


class StrategyCreate(CustomBaseModel):
    """创建策略请求"""

    name: str = Field(..., min_length=1, max_length=255, description="策略名称")
    slice_ids: list[int] = Field(default_factory=list, description="关联切片ID列表（可选）")
    brand_brief: BrandBrief | None = Field(None, description="结构化 Brand Brief（可选）")
    participant_ids: list[int] = Field(default_factory=list, description="参与者用户ID列表")


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
    """确认研究计划，创建 SocialMonitor + 探测任务"""

    research_design: dict[str, Any] = Field(
        ..., description="用户编辑后的研究计划（完整 JSON）"
    )
    notes_per_task: int = Field(
        50, ge=10, le=100, description="每个任务的全量采集数量"
    )
    probe_notes: int = Field(
        20, ge=20, le=20, description="每个任务的探测采集数量（固定 20 条）"
    )


class ConfirmResearchResponse(CustomBaseModel):
    """确认研究计划响应"""

    created_monitor_id: int
    created_task_count: int
    created_news_task_count: int = 0
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
    """关键词调整项，支持三种操作：
    - 替换：task_id + new_keyword
    - 移除：task_id + new_keyword=None
    - 新增：task_id=None + new_keyword + dimension
    """

    task_id: int | None = Field(None, description="要操作的任务 ID；为 None 时表示新增任务")
    new_keyword: str | None = Field(None, description="新关键词；为 None 时仅移除旧任务")
    platform: str = Field(..., description="平台代码")
    dimension: str | None = Field(None, description="新增任务所属维度（task_id=None 时必填）")

    @model_validator(mode="after")
    def validate_operation(self) -> "RefinementItem":
        if self.task_id is None:
            if not self.new_keyword:
                raise ValueError("新增任务时 new_keyword 不能为空")
            if not self.dimension:
                raise ValueError("新增任务时 dimension 不能为空")
        return self


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
    keyword: str = ""
    platform: str = ""
    status: str
    posts_count: int = 0
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

    @classmethod
    def from_orm_full(cls, strategy: "Strategy") -> "StrategyListItem":
        return cls(
            id=strategy.id,
            name=strategy.name,
            status=strategy.status,
            slice_count=len(strategy.slices),
            created_by=strategy.created_by,
            creator_name=strategy.creator.username if strategy.creator else "",
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )


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
    social_monitor_id: int | None = None
    news_monitor_id: int | None = None
    slices: list[SliceSummary] = Field(default_factory=list)

    # 参与者
    participant_ids: list[int] = Field(default_factory=list)
    participant_usernames: list[str] = Field(default_factory=list)

    # 元信息
    created_by: int
    creator_name: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_full(cls, strategy: "Strategy") -> "StrategyRead":
        """从 ORM Strategy 对象构造，处理所有跨关联字段。
        要求 strategy.slices → .slice → .monitor 已预加载（selectinload）。
        """
        slices = [
            SliceSummary(
                slice_id=ss.slice_id,
                slice_name=ss.slice.name if ss.slice else None,
                monitor_id=ss.slice.monitor_id if ss.slice else 0,
                monitor_name=(
                    ss.slice.monitor.name if ss.slice and ss.slice.monitor else ""
                ),
            )
            for ss in strategy.slices
        ]
        participants = getattr(strategy, "participants", []) or []
        return cls(
            id=strategy.id,
            name=strategy.name,
            status=strategy.status,
            brand_brief=strategy.brand_brief,
            research_design=strategy.research_design,
            probe_review_result=strategy.probe_review_result,
            probe_round=strategy.probe_round,
            coverage_check_result=strategy.coverage_check_result,
            output_type=strategy.output_type,
            phase1_result=strategy.phase1_result,
            phase2_result=strategy.phase2_result,
            phase3_result=strategy.phase3_result,
            social_monitor_id=strategy.social_monitor_id,
            news_monitor_id=strategy.news_monitor_id,
            slices=slices,
            participant_ids=[p.id for p in participants],
            participant_usernames=[p.username for p in participants],
            created_by=strategy.created_by,
            creator_name=strategy.creator.username if strategy.creator else "",
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )


class StrategyParticipantAssignment(CustomBaseModel):
    """策略参与者批量添加请求"""

    user_ids: list[int] = Field(..., min_length=1, description="要添加的参与者用户ID列表")


StrategyListResponse = PaginatedResponse[StrategyListItem]


# ==================== Brief 文档解析 ====================


class ParseBriefResponse(CustomBaseModel):
    """从上传文档解析出的 Brief 预填字段"""

    strategy_name: str = Field("", description="建议策略名称")
    subject: str = Field("", description="研究主体（品牌/产品/品类）")
    analysis_goal: str = Field("", description="分析目标")
    constraints: str = Field("", description="补充说明")
    platform_verdict: str = Field("partial", description="当前平台支持度: sufficient / partial / insufficient")
    platform_note: str = Field("", description="支持度说明（1-2句）")
    channel_plan: list[ChannelPlanItem] = Field(
        default_factory=list, description="渠道分发建议"
    )
