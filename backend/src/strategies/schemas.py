"""策略定义 Pydantic Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from src.schemas import CustomBaseModel, PaginatedResponse

if TYPE_CHECKING:
    from src.strategies.models import Strategy


# 产出路径：
#   brand_strategy 填充 insight_result / brand_role_result / big_idea_result（三层递进）
#   market_report  填充 agenda_map_result / landscape_result / strategic_brief_result（三层递进）
OutputType = Literal["brand_strategy", "market_report"]

# 主数据源：决定产出路径（brand_strategy vs market_report）
PrimarySource = Literal["social_media", "news_media"]


# ==================== Brand Brief ====================


class ChannelPlanItem(CustomBaseModel):
    """渠道分发条目"""

    type: str = Field(description="渠道类型: social_media / news_media / research_agent")
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


class StageResultEdit(CustomBaseModel):
    """编辑阶段结果请求"""

    result: dict = Field(..., description="阶段结果 JSON")


# ==================== 研究设计 Schemas ====================


class DesignResearchRequest(CustomBaseModel):
    """AI 研究设计请求"""

    user_input: str = Field("", description="用户补充说明（可为空，AI 将基于 Brief 直接设计）")


class DesignResearchResponse(CustomBaseModel):
    """AI 研究设计响应

    primary_sources / output_type 由 research_design_chain 根据决策表硬性推导：
    - 含 social_media 维度 → primary_sources 含 social_media；默认 output_type=brand_strategy
    - 仅含 news_media 维度 → primary_sources=[news_media]；强制 output_type=market_report
    """

    understanding_summary: str = Field("", description="AI 对分析需求的理解")
    research_questions: list[dict[str, Any]] = Field(default_factory=list)
    data_plan: list[dict[str, Any]] = Field(default_factory=list)
    slice_blueprint: list[dict[str, Any]] = Field(default_factory=list)
    primary_sources: list[PrimarySource] = Field(
        default_factory=list,
        description="本次研究计划的主数据源（按 data_plan 维度推导），brand_strategy 必须含 social_media",
    )
    output_type: OutputType = Field("brand_strategy")
    output_type_rationale: str = Field("")


class ConfirmResearchRequest(CustomBaseModel):
    """确认研究计划，创建 SocialMonitor + 探测任务

    output_type 由用户在前端显式选择并回传，后端校验其是否满足决策表：
    - brand_strategy 要求 research_design.primary_sources 包含 social_media
    - market_report 无社媒硬性要求，news_media-only 场景下会被前端强制选中
    """

    research_design: dict[str, Any] = Field(
        ..., description="用户编辑后的研究计划（完整 JSON）"
    )
    output_type: OutputType = Field(
        ..., description="用户显式选择的产出路径，后端会校验与 primary_sources 的一致性"
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


class SocialProbeTaskStatus(CustomBaseModel):
    """单个探测任务状态"""

    task_id: int
    keyword: str = ""
    platform: str = ""
    status: str = Field(..., description="任务状态")
    has_analysis: bool = Field(False, description="是否已有分析结果")


class ResearchAgentStatus(CustomBaseModel):
    """Research Agent 任务状态（不阻塞主流程）"""

    has_task: bool = Field(False, description="是否有关联的研究任务")
    status: str = Field("", description="研究任务状态: pending / running / completed / failed")
    task_id: int | None = Field(None, description="研究任务 ID")


class NewsProbeTaskStatus(CustomBaseModel):
    """单个新闻探测任务状态"""

    task_id: int
    keyword: str = ""
    dimension: str = ""
    status: str = Field(..., description="任务状态")
    completed: bool = Field(False, description="是否已完成（搜索落库完毕）")
    articles_count: int = Field(0, description="搜索到的文章数")


class ProbeStatusResponse(CustomBaseModel):
    """探测进度响应"""

    all_analyzed: bool = Field(False, description="所有探测任务是否都已完成分析")
    social_tasks: list[SocialProbeTaskStatus] = Field(default_factory=list)
    news_tasks: list[NewsProbeTaskStatus] = Field(default_factory=list)
    analyzed_count: int = 0
    total_count: int = 0
    probe_review_result: dict | None = Field(None, description="审查结果（全部分析完成后自动填充）")
    research_agent: ResearchAgentStatus = Field(
        default_factory=ResearchAgentStatus,
        description="Research Agent 研究任务状态���与探测并行，不阻塞）",
    )
    strategy: "StrategyRead | None" = None


class ApproveProbeResponse(CustomBaseModel):
    """手动确认探测通过响应"""

    approved_task_count: int
    strategy: "StrategyRead"


class SocialRefinementItem(CustomBaseModel):
    """社媒关键词调整项，支持三种操作：
    - 替换：task_id + new_keyword
    - 移除：task_id + new_keyword=None
    - 新增：task_id=None + new_keyword + dimension
    """

    task_id: int | None = Field(None, description="要操作的任务 ID；为 None 时表示新增任务")
    new_keyword: str | None = Field(None, description="新关键词；为 None 时仅移除旧任务")
    platform: str = Field(..., description="平台代码")
    dimension: str | None = Field(None, description="新增任务所属维度（task_id=None 时必填）")

    @model_validator(mode="after")
    def validate_operation(self) -> "SocialRefinementItem":
        if self.task_id is None:
            if not self.new_keyword:
                raise ValueError("新增任务时 new_keyword 不能为空")
            if not self.dimension:
                raise ValueError("新增任务时 dimension 不能为空")
        return self


class NewsRefinementItem(CustomBaseModel):
    """新闻 probe 任务的调整项（与 SocialRefinementItem 对齐语义）

    - 替换：task_id + new_keyword
    - 移除：task_id + new_keyword=None
    - 新增：task_id=None + new_keyword + dimension
    """

    task_id: int | None = Field(None, description="要操作的新闻任务 ID；为 None 时表示新增任务")
    new_keyword: str | None = Field(None, description="新关键词；为 None 时仅移除旧任务")
    dimension: str | None = Field(None, description="新增任务所属维度（task_id=None 时必填）")

    @model_validator(mode="after")
    def validate_operation(self) -> "NewsRefinementItem":
        if self.task_id is None:
            if not self.new_keyword:
                raise ValueError("新增任务时 new_keyword 不能为空")
            if not self.dimension:
                raise ValueError("新增任务时 dimension 不能为空")
        return self


class RefineProbeRequest(CustomBaseModel):
    """调整关键词请求（社媒 / 新闻两个渠道独立批量调整）"""

    social_refinements: list[SocialRefinementItem] = Field(
        default_factory=list, description="社媒任务调整列表"
    )
    news_refinements: list[NewsRefinementItem] = Field(
        default_factory=list, description="新闻任务调整列表"
    )

    @model_validator(mode="after")
    def validate_not_empty(self) -> "RefineProbeRequest":
        if not self.social_refinements and not self.news_refinements:
            raise ValueError("social_refinements 与 news_refinements 至少提供一项")
        return self


class RefineProbeResponse(CustomBaseModel):
    """调整关键词响应"""

    removed_social_task_ids: list[int] = Field(default_factory=list)
    created_social_task_ids: list[int] = Field(default_factory=list)
    removed_news_task_ids: list[int] = Field(default_factory=list)
    created_news_task_ids: list[int] = Field(default_factory=list)
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
    research_agent: ResearchAgentStatus = Field(
        default_factory=ResearchAgentStatus,
        description="Research Agent 研究任务状态（不阻塞采集流程）",
    )
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
    user_id: int
    user_username: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_full(cls, strategy: "Strategy") -> "StrategyListItem":
        return cls(
            id=strategy.id,
            name=strategy.name,
            status=strategy.status,
            slice_count=len(strategy.slices),
            user_id=strategy.user_id,
            user_username=strategy.user.username if strategy.user else "",
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
    output_type: OutputType | None = None
    # brand_strategy 路径（insight → brand_role → big_idea）
    insight_result: dict | None = None
    brand_role_result: dict | None = None
    big_idea_result: dict | None = None
    # market_report 路径（agenda_map → landscape → strategic_brief）
    agenda_map_result: dict | None = None
    landscape_result: dict | None = None
    strategic_brief_result: dict | None = None

    # 关联
    social_monitor_id: int | None = None
    news_monitor_id: int | None = None
    slices: list[SliceSummary] = Field(default_factory=list)

    # 参与者
    participant_ids: list[int] = Field(default_factory=list)
    participant_usernames: list[str] = Field(default_factory=list)

    # 元信息
    user_id: int
    user_username: str
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
            output_type=strategy.output_type,  # type: ignore[arg-type]
            insight_result=strategy.insight_result,
            brand_role_result=strategy.brand_role_result,
            big_idea_result=strategy.big_idea_result,
            agenda_map_result=strategy.agenda_map_result,
            landscape_result=strategy.landscape_result,
            strategic_brief_result=strategy.strategic_brief_result,
            social_monitor_id=strategy.social_monitor_id,
            news_monitor_id=strategy.news_monitor_id,
            slices=slices,
            participant_ids=[p.id for p in participants],
            participant_usernames=[p.username for p in participants],
            user_id=strategy.user_id,
            user_username=strategy.user.username if strategy.user else "",
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
    platform_verdict: str = Field(
        "partial",
        description="当前平台支持度: sufficient / partial / insufficient",
    )
    platform_note: str = Field("", description="支持度说明（1-2句）")
    channel_plan: list[ChannelPlanItem] = Field(
        default_factory=list, description="渠道分发建议"
    )
