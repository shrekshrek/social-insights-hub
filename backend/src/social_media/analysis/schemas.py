"""分析模块 Pydantic 模型

统一使用 AnalysisJob 模型记录所有模块（社媒/新闻/策略）的 LLM 分析调用。
"""

from datetime import datetime
from typing import Literal
from pydantic import Field

from src.schemas import CustomBaseModel
from src.social_media.analysis.constants import SPAM_HIGH_THRESHOLD


# ==================== Token 使用统计 ====================


class CallDetail(CustomBaseModel):
    """单次LLM调用详情"""

    call_index: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_cny: float
    duration_seconds: float
    timestamp: datetime | None = None


class TokenUsageSummary(CustomBaseModel):
    """Token使用汇总"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_cny: float = 0.0
    total_duration_seconds: float = 0.0
    avg_tokens_per_call: float = 0.0
    avg_cost_per_call: float = 0.0


class TokenUsageStats(CustomBaseModel):
    """Token使用统计"""

    summary: TokenUsageSummary = Field(default_factory=TokenUsageSummary)
    call_details: list[CallDetail] = []


# ==================== 提取结果 Schema ====================


class EntityInfo(CustomBaseModel):
    """实体信息"""

    name: str = Field(..., description="实体名称")
    type: Literal["品牌", "产品", "服务", "人物", "其他"] = Field(
        ..., description="实体类型"
    )
    sentiment: Literal[1, 0, -1] = Field(..., description="情感倾向")
    features: list[str] = Field(default_factory=list, description="特性/功能/亮点")
    issues: list[str] = Field(default_factory=list, description="问题/缺点")
    expectations: list[str] = Field(default_factory=list, description="改进期望/建议")
    audience: list[str] = Field(default_factory=list, description="目标人群")
    scenarios: list[str] = Field(default_factory=list, description="使用场景")
    market_factors: list[str] = Field(default_factory=list, description="价格/促销信息")
    competitors: list[str] = Field(default_factory=list, description="竞品对比")


class GeneralOpinion(CustomBaseModel):
    """通用观点"""

    category: str = Field(..., description="观点类别")
    opinions: list[str] = Field(default_factory=list, description="具体观点")
    sentiment: Literal[1, 0, -1] = Field(..., description="情感倾向")


class PostDeepResult(CustomBaseModel):
    """原文深度分析结果"""

    entities: list[EntityInfo] = Field(default_factory=list, description="识别的实体")
    general_opinions: list[GeneralOpinion] = Field(
        default_factory=list, description="通用观点"
    )
    summary: str = Field(..., description="内容摘要（100-200字）")


# ==================== 评论专用 Schema（带来源追踪）====================


class CommentEntityInfo(CustomBaseModel):
    """评论中提取的实体信息（带来源追踪）"""

    name: str = Field(..., description="实体名称")
    type: Literal["品牌", "产品", "服务", "人物", "其他"] = Field(
        ..., description="实体类型"
    )
    sentiment: Literal[1, 0, -1] = Field(..., description="情感倾向")
    features: list[str] = Field(default_factory=list, description="特性/功能/亮点")
    issues: list[str] = Field(default_factory=list, description="问题/缺点")
    expectations: list[str] = Field(default_factory=list, description="改进期望/建议")
    audience: list[str] = Field(default_factory=list, description="目标人群")
    scenarios: list[str] = Field(default_factory=list, description="使用场景")
    market_factors: list[str] = Field(default_factory=list, description="价格/促销信息")
    competitors: list[str] = Field(default_factory=list, description="竞品对比")
    # 评论来源追踪
    source_comments: list[int] = Field(
        default_factory=list, description="来源评论编号列表"
    )
    support_score: int = Field(
        default=0, description="支持度分数（来源评论点赞数之和）"
    )


class CommentGeneralOpinion(CustomBaseModel):
    """评论中提取的通用观点（带来源追踪）"""

    category: str = Field(..., description="观点类别")
    opinions: list[str] = Field(default_factory=list, description="具体观点")
    sentiment: Literal[1, 0, -1] = Field(..., description="情感倾向")
    # 评论来源追踪
    source_comments: list[int] = Field(
        default_factory=list, description="来源评论编号列表"
    )
    support_score: int = Field(
        default=0, description="支持度分数（来源评论点赞数之和）"
    )


class CommentDeepResult(CustomBaseModel):
    """评论深度分析结果（按原文聚合，带来源追踪）"""

    entities: list[CommentEntityInfo] = Field(
        default_factory=list, description="识别的实体（带来源追踪）"
    )
    general_opinions: list[CommentGeneralOpinion] = Field(
        default_factory=list, description="通用观点（带来源追踪）"
    )


# ==================== PostAnalysis Schema ====================


class PostAnalysisCreate(CustomBaseModel):
    """创建原文分析"""

    task_id: int = Field(..., gt=0, description="任务ID")
    post_id: int = Field(..., gt=0, description="原文ID")
    spam_score: float | None = Field(None, ge=0, le=10)
    value_score: float | None = Field(None, ge=0, le=10)
    relevance_score: float | None = Field(None, ge=0, le=10)
    sentiment: int | None = Field(
        None, ge=-2, le=2, description="情感倾向（-2强烈负面 到 2强烈正面）"
    )
    post_deep_result: dict | None = None
    comment_deep_result: dict | None = None


class PostAnalysisUpdate(CustomBaseModel):
    """更新原文分析"""

    spam_score: float | None = Field(None, ge=0, le=10)
    value_score: float | None = Field(None, ge=0, le=10)
    relevance_score: float | None = Field(None, ge=0, le=10)
    sentiment: int | None = Field(
        None, ge=-2, le=2, description="情感倾向（-2强烈负面 到 2强烈正面）"
    )
    cii: float | None = Field(None, ge=0, description="内容互动指数")
    post_deep_result: dict | None = None
    comment_deep_result: dict | None = None
    analyzed_at: datetime | None = None
    analysis_model: str | None = None


class PostAnalysisResponse(CustomBaseModel):
    """原文分析完整响应"""

    id: int
    task_id: int
    post_id: int

    # 初筛分析
    spam_score: float | None = None
    value_score: float | None = None
    relevance_score: float | None = None
    sentiment: int | None = None

    # 互动指数
    cii: float | None = None

    # 深度分析
    post_deep_result: PostDeepResult | None = None
    comment_deep_result: CommentDeepResult | None = None

    # 元数据
    analyzed_at: datetime | None = None
    analysis_model: str | None = None
    created_at: datetime
    updated_at: datetime


# ==================== AnalysisJob Schema ====================


class AnalysisJobCreate(CustomBaseModel):
    """创建分析任务"""

    social_monitor_id: int | None = Field(None, gt=0, description="社媒监测项目ID")
    social_task_id: int | None = Field(None, gt=0, description="社媒采集任务ID")
    news_monitor_id: int | None = Field(None, gt=0, description="新闻监测项目ID")
    news_task_id: int | None = Field(None, gt=0, description="新闻采集任务ID")
    analysis_type: str = Field(..., description="分析类型")
    celery_task_id: str = Field(..., description="Celery任务ID")
    source_count: int = Field(0, ge=0, description="源数据数量")
    analysis_config: dict | None = Field(None, description="分析配置")
    source_task_ids: list[int] | None = Field(None, description="源任务ID列表")


class AnalysisJobUpdate(CustomBaseModel):
    """更新分析任务"""

    status: str | None = None
    result_data: dict | None = None
    analysis_summary: str | None = None
    analyzed_count: int | None = None
    failed_count: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time: int | None = None
    token_usage: TokenUsageStats | None = None
    error_message: str | None = None


class AnalysisJobResponse(CustomBaseModel):
    """分析任务响应"""

    id: int
    social_monitor_id: int | None = None
    social_task_id: int | None = None
    news_monitor_id: int | None = None
    news_task_id: int | None = None
    user_id: int
    analysis_type: str
    celery_task_id: str
    status: str

    # 配置
    analysis_config: dict | None = None
    source_task_ids: list[int] | None = None

    # 统计
    source_count: int
    analyzed_count: int
    failed_count: int

    # 结果
    result_data: dict | None = None
    analysis_summary: str | None = None

    # 性能
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_time: int | None = None
    token_usage: TokenUsageStats | None = None

    # 错误
    error_message: str | None = None

    # 时间戳
    created_at: datetime
    updated_at: datetime

    # 关联信息（可选，用于列表展示）
    social_monitor_name: str | None = None
    social_task_name: str | None = None
    news_monitor_name: str | None = None
    news_task_name: str | None = None
    slice_id: int | None = None
    slice_name: str | None = None
    user_name: str | None = None


class AnalysisJobListResponse(CustomBaseModel):
    """分析任务列表响应"""

    items: list[AnalysisJobResponse]
    total: int
    page: int
    page_size: int


# ==================== 深度分析预览 ====================


class DeepAnalysisPreviewResponse(CustomBaseModel):
    """基于阈值的深度分析预览结果"""

    total_posts: int
    screened_count: int
    qualified_count: int  # 符合阈值条件的已初筛原文总数（不管是否已深度分析）
    matched_count: int  # 符合条件且待深度分析的原文数
    deep_done: int
    comment_done: int
    deep_candidate_ids: list[int]
    comment_candidate_ids: list[int]


# ==================== API 请求 Schema ====================


class RunScreeningRequest(CustomBaseModel):
    """运行原文初筛请求"""

    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: list[int] | None = Field(
        None, description="指定的原文ID列表，为空则分析所有"
    )
    analyze_all: bool = Field(False, description="是否分析所有原文")


class RunDeepAnalysisRequest(CustomBaseModel):
    """运行深度分析请求"""

    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: list[int] | None = Field(
        None, description="指定的原文ID列表，为空则分析所有"
    )
    analysis_focus: list[str] | None = Field(None, description="分析重点（预留扩展）")


# ==================== Project Slice (Manual) ====================


class CreateProjectSliceRequest(CustomBaseModel):
    """手动生成项目级合并分析切片（不依赖 query/filter_spec）"""

    task_ids: list[int] = Field(..., min_length=1, description="参与合并的任务ID列表")
    name: str | None = Field(None, max_length=255, description="切片名称（可选）")
    subject: str | None = Field(
        None,
        max_length=200,
        description="主体品牌/产品（用于 Focus 层触发与角色仲裁；为空则跳过 Focus 层）",
    )
    competitors: list[str] | None = Field(
        None,
        description="竞品列表（用于角色仲裁与 Focus 层对比）",
    )
    platform_weights: dict[str, float] | None = Field(
        None,
        description="平台权重覆盖（key=platform code，如 bilibili/xhs/douyin/weibo；value=权重系数）",
    )


class ProjectSliceResponse(CustomBaseModel):
    id: int
    name: str | None = None
    monitor_id: int
    user_id: int
    included_task_ids: list[int]
    result_data: dict
    created_at: datetime
    updated_at: datetime


class ProjectSliceListResponse(CustomBaseModel):
    items: list[ProjectSliceResponse]


class UpdateProjectSliceRequest(CustomBaseModel):
    """更新切片（仅支持改名）"""

    name: str = Field(..., min_length=1, max_length=255, description="切片名称")


class RunAnalysisResponse(CustomBaseModel):
    """启动分析任务响应"""

    celery_task_id: str
    job_id: int | None = None  # 聚合分析不创建 AnalysisJob，所以可能为 None
    status: str
    message: str


# ==================== 分析进度查询 Schema ====================


class AnalysisProgressResponse(CustomBaseModel):
    """分析进度响应"""

    job_id: int
    status: str
    progress: float  # 0-100
    analyzed_count: int
    total_count: int
    estimated_time_remaining: int | None = None  # 秒
    current_cost: float  # 当前成本（元）
    current_tokens: int  # 当前token消耗


# ==================== 分析统计 Schema ====================


class AnalysisStatsResponse(CustomBaseModel):
    """分析统计响应"""

    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    pending_jobs: int
    processing_jobs: int
    total_cost_cny: float
    total_tokens: int
    avg_processing_time: float


# ==================== 任务级聚合结果 Schema ====================


class TaskAnalysisDataVolume(CustomBaseModel):
    """数据量统计"""

    total: int = Field(0, description="总原文数")
    screened: int = Field(0, description="已初筛数")
    deep_analyzed: int = Field(0, description="已深度分析数")
    comment_analyzed: int = Field(0, description="已评论分析数")


class MarketingAnalysis(CustomBaseModel):
    """营销浓度分析"""

    promotion_ratio: float = Field(0.0, description="营销内容占比 (0-1)")
    organic_ratio: float = Field(1.0, description="自然内容占比 (0-1)")
    promotion_count: int = Field(0, description="营销原文数")
    organic_count: int = Field(0, description="自然原文数")


class SentimentConflict(CustomBaseModel):
    """舆论反差度分析"""

    avg_conflict: float = Field(0.0, description="平均反差度 (绝对值)")
    conflict_direction: str = Field(
        "aligned",
        description="反差方向: post_positive(原文更正面)/comment_positive(评论更正面)/aligned(一致)",
    )
    high_conflict_count: int = Field(0, description="高反差原文数 (|差值| > 1)")
    risk_level: str = Field("low", description="风险等级: low/medium/high")


# ==================== Spam 分布 Schema ====================


class SpamSourceBreakdown(CustomBaseModel):
    """单个 spam 组内的原文/评论拆分"""

    total: int = 0
    post: int = 0
    comment: int = 0


class SpamDistribution(CustomBaseModel):
    """实体/观点的 spam 4 维分布"""

    high_spam: SpamSourceBreakdown = Field(default_factory=SpamSourceBreakdown)
    low_spam: SpamSourceBreakdown = Field(default_factory=SpamSourceBreakdown)


class SpamCountBreakdown(CustomBaseModel):
    """简化的 spam 分组计数 (无原文/评论拆分)"""

    high: int = 0
    low: int = 0


class SpamConfig(CustomBaseModel):
    """Spam 分组配置"""

    threshold: float = SPAM_HIGH_THRESHOLD


class NsrBySpam(CustomBaseModel):
    """按 spam 分组的 NSR"""

    high: float = 0
    low: float = 0


# ==================== 核心指标 ====================


class TaskAnalysisMetrics(CustomBaseModel):
    """核心指标"""

    nsr: float = Field(0.0, description="净情感率 (Net Sentiment Rate), 范围 [-2, +2]")
    avg_cii: float = Field(0.0, description="平均互动指数 (Content Interaction Index)")
    serp_health: float = Field(50.0, description="搜索健康度, 范围 [0, 100]")
    marketing_analysis: MarketingAnalysis = Field(
        default_factory=MarketingAnalysis, description="营销浓度分析"
    )
    sentiment_conflict: SentimentConflict = Field(
        default_factory=SentimentConflict, description="舆论反差度分析"
    )
    nsr_by_spam: NsrBySpam | None = None


class QuadrantItem(CustomBaseModel):
    """四象限数据项"""

    post_id: int
    x: float = Field(..., description="情感分, 范围 [-2, +2]")
    y: float = Field(..., description="CII 互动指数")
    quadrant: str = Field(
        ..., description="象限: Q1_danger/Q2_brand/Q3_complaint/Q4_niche/neutral"
    )
    label: str = Field("", description="标签（摘要前20字）")
    spam_group: str | None = None


class QuadrantSummary(CustomBaseModel):
    """四象限统计"""

    Q1_danger: int = Field(0, description="爆雷区（高互动/负面）")
    Q2_brand: int = Field(0, description="品牌区（高互动/正面）")
    Q3_complaint: int = Field(0, description="吐槽区（低互动/负面）")
    Q4_niche: int = Field(0, description="自嗨区（低互动/正面）")
    neutral: int = Field(0, description="中性区")


class TimeDistributionItem(CustomBaseModel):
    """时间分布数据项"""

    date: str = Field(..., description="日期 (YYYY-MM-DD)")
    count: int = Field(0, description="原文数量")
    post_ids: list[int] = Field(
        default_factory=list, description="该日期对应的原文ID列表，用于反向追溯"
    )
    spam_breakdown: SpamCountBreakdown | None = None


class Freshness(CustomBaseModel):
    """数据新鲜度"""

    last_7_days: float = Field(0.0, description="最近7天原文占比 (0-1)")
    last_30_days: float = Field(0.0, description="最近30天原文占比 (0-1)")
    avg_age_days: float = Field(0.0, description="平均发布天数")


# ==================== 新增派生分析图表 Schema ====================


class OriginalTerm(CustomBaseModel):
    """原始观点词条"""

    text: str
    count: int = 1


class IpaPoint(CustomBaseModel):
    """IPA 分析点"""

    name: str
    x: float = Field(..., description="关注度 (Mentions)")
    y: float = Field(..., description="满意度 (Sentiment)")
    z: float = Field(0, description="气泡大小 (Log Smoothed Heat)")
    heat: float = Field(0, description="影响力 (Heat)")
    post_ids: list[int] = Field(default_factory=list)
    spam_distribution: SpamDistribution | None = None
    original_terms: list[OriginalTerm] | None = Field(
        None, description="原始观点列表（仅当该点为观点集合时存在）"
    )


class IpaQuadrants(CustomBaseModel):
    """IPA 象限数据"""

    strength: list[IpaPoint] = Field(default_factory=list, description="优势区")
    improvement: list[IpaPoint] = Field(default_factory=list, description="改进区")
    maintain: list[IpaPoint] = Field(default_factory=list, description="维持区")
    opportunity: list[IpaPoint] = Field(default_factory=list, description="机会区")


class IpaThresholds(CustomBaseModel):
    """IPA 阈值"""

    x: float
    y: float


class IpaAnalysis(CustomBaseModel):
    """IPA 分析结果"""

    quadrants: IpaQuadrants = Field(default_factory=IpaQuadrants)
    thresholds: IpaThresholds = Field(default_factory=lambda: IpaThresholds(x=0, y=0))


class ContextNode(CustomBaseModel):
    """关联网络节点"""

    name: str
    type: str = Field(..., description="类型: audience/scenario/topic")
    weight: float = Field(..., description="关联权重")
    co_occurrence: int = Field(..., description="共现次数")
    sentiment: float | None = None
    post_ids: list[int] = Field(default_factory=list)


class ContextEdge(CustomBaseModel):
    """关联网络边"""

    source: str
    target: str
    value: float


class ContextGraph(CustomBaseModel):
    """关联网络图"""

    center_node: str | None = None
    nodes: list[ContextNode] = Field(default_factory=list)
    edges: list[ContextEdge] = Field(default_factory=list)


class ContextGraphWithDimensions(CustomBaseModel):
    """关联网络图（按 spam 维度拆分的三层结构）"""

    all: ContextGraph = Field(..., description="全部数据")
    organic: ContextGraph = Field(..., description="仅有机内容")
    promo: ContextGraph = Field(..., description="仅推广内容")


class SentimentDistribution(CustomBaseModel):
    """情感分布"""

    positive: int = Field(0, description="正面提及次数")
    negative: int = Field(0, description="负面提及次数")
    neutral: int = Field(0, description="中性提及次数")


class CompetitorSeries(CustomBaseModel):
    """竞品雷达系列数据"""

    name: str
    data: list[float] | None = None  # 雷达图数据
    sentiment: float | None = None  # 柱状图数据
    sentiment_distribution: SentimentDistribution | None = None  # 柱状图数据
    products: list[str] | None = None  # 品牌聚合时包含的产品列表
    post_ids: list[int] = Field(default_factory=list)
    spam_distribution: SpamDistribution | None = None


class CompetitorRadar(CustomBaseModel):
    """竞品雷达分析"""

    mode: Literal["radar", "bar", "none"] = "none"
    dimensions: list[str] | None = None
    series: list[CompetitorSeries] = Field(default_factory=list)


class CompetitorRadarWithDimensions(CustomBaseModel):
    """竞品雷达分析（按 spam 维度拆分的三层结构）"""

    all: CompetitorRadar = Field(..., description="全部数据")
    organic: CompetitorRadar = Field(..., description="仅有机内容")
    promo: CompetitorRadar = Field(..., description="仅推广内容")


class TaskAnalysisCharts(CustomBaseModel):
    """图表数据"""

    quadrant: list[QuadrantItem] = Field(default_factory=list, description="四象限数据")
    quadrant_summary: QuadrantSummary = Field(
        default_factory=QuadrantSummary, description="四象限统计"
    )
    time_distribution: list[TimeDistributionItem] = Field(
        default_factory=list, description="时间分布"
    )
    time_distribution_skipped: int = Field(
        0, description="无发布时间的原文数量"
    )
    # 新增图表字段
    ipa_analysis: IpaAnalysis | None = None
    context_graph: ContextGraphWithDimensions | None = None
    competitor_radar: CompetitorRadarWithDimensions | None = None


class SourceDistribution(CustomBaseModel):
    """来源分布（原文 vs 评论）"""

    post: float = Field(0.0, description="来自原文的占比 (0-1)")
    comment: float = Field(0.0, description="来自评论的占比 (0-1)")


class EntityNormalizedInfo(CustomBaseModel):
    """实体归一化信息"""

    aliases: list[str] = Field(default_factory=list)
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)


class EntityTags(CustomBaseModel):
    """实体多维标签"""

    role: str = Field("Context", description="角色: Target/Competitor/Context")
    parent: str = Field("", description="品牌归属")


class EntityStat(CustomBaseModel):
    """实体统计"""

    name: str = Field(..., description="实体名称")
    type: str = Field("其他", description="实体类型")
    role: str = Field(
        "other",
        description="主体角色: target(本品)/competitor(竞品)/other(其他有价值实体)",
    )
    heat: float = Field(0, description="热度（CII加权）")
    mentions: int = Field(0, description="唯一原文提及数")
    score: float = Field(0, description="综合评分")
    sentiment: float = Field(0, description="派生情感值 [-1, 1]，CII加权")
    sentiment_distribution: SentimentDistribution = Field(
        default_factory=SentimentDistribution, description="情感分布"
    )
    source_distribution: SourceDistribution = Field(
        default_factory=SourceDistribution, description="来源分布"
    )
    # 直接返回详细项（含 original_terms），用于 UI 溯源展示
    top_features: list[dict] = Field(
        default_factory=list, description="主要特性（详细项，含原始词条）"
    )
    top_issues: list[dict] = Field(
        default_factory=list, description="主要问题（详细项，含原始词条）"
    )
    top_expectations: list[dict] = Field(
        default_factory=list, description="主要期望（详细项，含原始词条）"
    )
    post_ids: list[int] = Field(
        default_factory=list, description="关联原文ID，用于反向追溯"
    )
    post_source_ids: list[int] = Field(
        default_factory=list, description="来自原文的原文ID列表"
    )
    comment_source_ids: list[int] = Field(
        default_factory=list, description="来自评论的原文ID列表"
    )
    spam_distribution: SpamDistribution | None = None
    tags: EntityTags | None = None  # 多维标签
    original_terms: list[dict] | None = None  # 原始词条（仅在合并时存在）
    normalized_info: EntityNormalizedInfo | None = None


class OpinionStat(CustomBaseModel):
    """观点统计"""

    name: str = Field(..., description="观点名称")
    category: str | None = None
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="唯一原文提及数")
    score: float = Field(0, description="综合评分")
    sentiment: float = Field(0, description="情感倾向")
    source_distribution: SourceDistribution = Field(
        default_factory=SourceDistribution, description="来源分布"
    )
    post_ids: list[int] = Field(
        default_factory=list, description="关联原文ID，用于反向追溯"
    )
    post_source_ids: list[int] = Field(
        default_factory=list, description="来自原文的原文ID列表"
    )
    comment_source_ids: list[int] = Field(
        default_factory=list, description="来自评论的原文ID列表"
    )
    spam_distribution: SpamDistribution | None = None
    original_terms: list[dict] | None = None  # 原始词条（仅在合并时存在）
    post_source_count: int = 0
    comment_source_count: int = 0


# ==================== 场景与人群画像 Schema ====================


class ScenarioStat(CustomBaseModel):
    """场景统计"""

    label: str = Field(..., description="场景标签")
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="提及数")
    associated_issues: list[str] = Field(default_factory=list, description="关联问题")
    associated_features: list[str] = Field(default_factory=list, description="关联特性")
    post_ids: list[int] = Field(
        default_factory=list, description="关联原文ID，用于反向追溯"
    )


class AudienceStat(CustomBaseModel):
    """人群画像统计"""

    label: str = Field(..., description="人群标签")
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="提及数")
    preferences: list[str] = Field(default_factory=list, description="偏好")
    post_ids: list[int] = Field(
        default_factory=list, description="关联原文ID，用于反向追溯"
    )


class ContextAnalysis(CustomBaseModel):
    """场景与人群画像"""

    scenarios: list[ScenarioStat] = Field(default_factory=list, description="使用场景")
    audiences: list[AudienceStat] = Field(default_factory=list, description="目标人群")


# ==================== 竞品分析 Schema ====================


class CompetitorDetail(CustomBaseModel):
    """竞品详情"""

    name: str = Field(..., description="竞品名称")
    sentiment: float = Field(0, description="情感倾向")
    sentiment_distribution: SentimentDistribution = Field(
        default_factory=SentimentDistribution, description="情感分布"
    )
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="提及数")
    post_ids: list[int] = Field(default_factory=list, description="关联原文ID")
    top_features: list[str] = Field(default_factory=list, description="主要特性")
    top_issues: list[str] = Field(default_factory=list, description="主要问题")


class Competition(CustomBaseModel):
    """竞品分析"""

    top_competitors: list[str] = Field(default_factory=list, description="主要竞品")
    comparison_sentiment: float = Field(0, description="对比情感（正=本品更好）")
    target_sentiment: float = Field(0, description="本品情感")
    competitor_sentiment: float = Field(0, description="竞品情感")
    competitor_details: list[CompetitorDetail] = Field(
        default_factory=list, description="竞品详情"
    )


# ==================== KOL 声音 Schema ====================


class KolVoice(CustomBaseModel):
    """KOL 声音"""

    author: str = Field(..., description="作者名称")
    title: str = Field("", description="原文标题")
    sentiment: float = Field(0, description="情感倾向")
    summary: str = Field("", description="观点摘要")
    post_id: int = Field(..., description="原文ID")
    cii: float = Field(0, description="互动指数")
    platform: str = Field("", description="平台来源")
    spam_group: str | None = None


# ==================== 洞察数据 Schema ====================


class TaskAnalysisInsights(CustomBaseModel):
    """洞察数据"""

    top_entities: list[EntityStat] = Field(
        default_factory=list, description="热门实体（全部）"
    )
    target_entities: list[EntityStat] = Field(
        default_factory=list, description="本品实体"
    )
    competitor_entities: list[EntityStat] = Field(
        default_factory=list, description="竞品实体"
    )
    top_topics: list[OpinionStat] = Field(default_factory=list, description="热门话题")
    kol_voices: list[KolVoice] = Field(default_factory=list, description="KOL 声音")


class TaskAnalysisMeta(CustomBaseModel):
    """元数据"""

    task_id: int | None = None
    analyzed_at: str | None = None
    keywords: list[str] = Field(default_factory=list, description="用于分析的关键词")
    data_volume: TaskAnalysisDataVolume = Field(default_factory=TaskAnalysisDataVolume)


class TaskAnalysisResultData(CustomBaseModel):
    """任务级分析聚合结果（存储在 AnalysisJob.result_data 中）"""

    meta: TaskAnalysisMeta = Field(default_factory=TaskAnalysisMeta)
    metrics: TaskAnalysisMetrics = Field(default_factory=TaskAnalysisMetrics)
    charts: TaskAnalysisCharts = Field(default_factory=TaskAnalysisCharts)
    freshness: Freshness = Field(default_factory=Freshness, description="数据新鲜度")
    insights: TaskAnalysisInsights = Field(default_factory=TaskAnalysisInsights)
    spam_config: SpamConfig | None = Field(None, description="Spam 分组配置")


class TaskAnalysisResultResponse(CustomBaseModel):
    """任务级聚合分析结果 API 响应"""

    task_id: int = Field(..., description="任务ID")
    analyzed_at: str | None = Field(None, description="聚合分析时间 (ISO格式)")
    result: TaskAnalysisResultData = Field(..., description="聚合分析结果")


class RunAggregationResponse(CustomBaseModel):
    """运行聚合分析响应"""

    success: bool = Field(..., description="是否成功")
    task_id: int = Field(..., description="任务ID")
    analyzed_at: str = Field(..., description="分析时间 (ISO格式)")
    result: TaskAnalysisResultData = Field(..., description="聚合分析结果")


# ==================== 原文分析列表 Schema ====================


class PostAnalysisWithPostInfo(CustomBaseModel):
    """带原文信息的分析结果"""

    # 原文基本信息
    post_id: int
    post_id_on_platform: str | None = None  # 平台上的原文ID，用于关联原文数据
    title: str | None = None
    content: str | None = None
    author_name: str | None = None
    likes_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    collected_count: int = 0
    views_count: int = 0
    danmaku_count: int = 0
    published_at: datetime | None = None
    url: str | None = None

    # 初筛分析
    spam_score: float | None = None
    value_score: float | None = None
    relevance_score: float | None = None
    sentiment: int | None = None

    # 互动指数
    cii: float | None = None

    # 深度分析
    post_deep_result: PostDeepResult | None = None
    comment_deep_result: CommentDeepResult | None = None

    # 元数据
    analyzed_at: datetime | None = None
    analysis_model: str | None = None


class PostAnalysisListResponse(CustomBaseModel):
    """原文分析列表响应"""

    items: list[PostAnalysisWithPostInfo]
    total: int
    page: int
    page_size: int
