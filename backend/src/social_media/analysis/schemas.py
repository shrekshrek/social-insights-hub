"""分析模块 Pydantic 模型

统一使用 AnalysisJob 模型，通过 task_id 是否为空区分任务级/项目级分析。
"""

from datetime import datetime
from typing import Literal
from pydantic import Field

from src.schemas import CustomBaseModel


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
    summary: TokenUsageSummary
    call_details: list[CallDetail] = []


# ==================== 提取结果 Schema ====================

class EntityInfo(CustomBaseModel):
    """实体信息"""
    name: str = Field(..., description="实体名称")
    type: Literal["品牌", "产品", "服务", "人物", "其他"] = Field(..., description="实体类型")
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
    """帖子深度分析结果"""
    entities: list[EntityInfo] = Field(default_factory=list, description="识别的实体")
    general_opinions: list[GeneralOpinion] = Field(default_factory=list, description="通用观点")
    summary: str = Field(..., description="内容摘要（100-200字）")


class CommentDeepResult(CustomBaseModel):
    """评论深度分析结果（按帖子聚合）"""
    entities: list[EntityInfo] = Field(default_factory=list, description="识别的实体")
    general_opinions: list[GeneralOpinion] = Field(default_factory=list, description="通用观点")


# ==================== PostAnalysis Schema ====================

class PostAnalysisCreate(CustomBaseModel):
    """创建帖子分析"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_id: int = Field(..., gt=0, description="帖子ID")
    spam_score: float | None = Field(None, ge=0, le=10)
    value_score: float | None = Field(None, ge=0, le=10)
    relevance_score: float | None = Field(None, ge=0, le=10)
    sentiment: int | None = Field(None, ge=-2, le=2, description="情感倾向（-2强烈负面 到 2强烈正面）")
    post_deep_result: dict | None = None
    comment_deep_result: dict | None = None


class PostAnalysisUpdate(CustomBaseModel):
    """更新帖子分析"""
    spam_score: float | None = Field(None, ge=0, le=10)
    value_score: float | None = Field(None, ge=0, le=10)
    relevance_score: float | None = Field(None, ge=0, le=10)
    sentiment: int | None = Field(None, ge=-2, le=2, description="情感倾向（-2强烈负面 到 2强烈正面）")
    cii: float | None = Field(None, ge=0, description="内容互动指数")
    post_deep_result: dict | None = None
    comment_deep_result: dict | None = None
    analyzed_at: datetime | None = None
    analysis_model: str | None = None


class PostAnalysisResponse(CustomBaseModel):
    """帖子分析完整响应"""
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
    project_id: int = Field(..., gt=0, description="项目ID")
    task_id: int | None = Field(None, gt=0, description="任务ID（任务级分析时必填）")
    analysis_type: str = Field(
        ...,
        pattern="^(screening_posts|deep_posts|deep_comments|topic_clustering|competitive)$",
        description="分析类型"
    )
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
    project_id: int
    task_id: int | None
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
    project_name: str | None = None
    task_name: str | None = None
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
    matched_count: int
    deep_done: int
    comment_done: int
    deep_candidate_ids: list[int]
    comment_candidate_ids: list[int]


# ==================== API 请求 Schema ====================

class RunScreeningRequest(CustomBaseModel):
    """运行帖子初筛请求"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: list[int] | None = Field(None, description="指定的帖子ID列表，为空则分析所有")
    analyze_all: bool = Field(False, description="是否分析所有帖子")


class RunDeepAnalysisRequest(CustomBaseModel):
    """运行深度分析请求"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: list[int] | None = Field(None, description="指定的帖子ID列表，为空则分析所有")
    analysis_focus: list[str] | None = Field(None, description="分析重点（预留扩展）")


class RunClusteringRequest(CustomBaseModel):
    """运行主题聚类分析请求（项目级分析）"""
    project_id: int = Field(..., gt=0, description="项目ID")
    task_ids: list[int] | None = Field(None, description="源任务ID列表")
    config: dict | None = Field(None, description="聚类配置")


class RunCompetitiveRequest(CustomBaseModel):
    """运行竞品分析请求（项目级分析）"""
    project_id: int = Field(..., gt=0, description="项目ID")
    task_ids: list[int] | None = Field(None, description="源任务ID列表")
    competitors: list[str] | None = Field(None, description="竞品列表")


class RunAnalysisResponse(CustomBaseModel):
    """启动分析任务响应"""
    celery_task_id: str
    job_id: int
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
    total: int = Field(0, description="总帖子数")
    screened: int = Field(0, description="已初筛数")
    deep_analyzed: int = Field(0, description="已深度分析数")
    comment_analyzed: int = Field(0, description="已评论分析数")


class MarketingAnalysis(CustomBaseModel):
    """营销浓度分析"""
    promotion_ratio: float = Field(0.0, description="营销内容占比 (0-1)")
    organic_ratio: float = Field(1.0, description="自然内容占比 (0-1)")
    promotion_count: int = Field(0, description="营销帖子数")
    organic_count: int = Field(0, description="自然帖子数")


class SentimentConflict(CustomBaseModel):
    """舆论反差度分析"""
    avg_conflict: float = Field(0.0, description="平均反差度 (绝对值)")
    conflict_direction: str = Field(
        "aligned",
        description="反差方向: post_positive(帖子更正面)/comment_positive(评论更正面)/aligned(一致)"
    )
    high_conflict_count: int = Field(0, description="高反差帖子数 (|差值| > 1)")
    risk_level: str = Field("low", description="风险等级: low/medium/high")


class TaskAnalysisMetrics(CustomBaseModel):
    """核心指标"""
    nsr: float = Field(0.0, description="净情感率 (Net Sentiment Rate), 范围 [-2, +2]")
    avg_cii: float = Field(0.0, description="平均互动指数 (Content Interaction Index)")
    serp_health: float = Field(50.0, description="搜索健康度, 范围 [0, 100]")
    marketing_analysis: MarketingAnalysis = Field(default_factory=MarketingAnalysis, description="营销浓度分析")
    sentiment_conflict: SentimentConflict = Field(default_factory=SentimentConflict, description="舆论反差度分析")


class QuadrantItem(CustomBaseModel):
    """四象限数据项"""
    post_id: int
    x: float = Field(..., description="情感分, 范围 [-2, +2]")
    y: float = Field(..., description="CII 互动指数")
    quadrant: str = Field(..., description="象限: Q1_danger/Q2_brand/Q3_complaint/Q4_niche/neutral")
    label: str = Field("", description="标签（摘要前20字）")


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
    count: int = Field(0, description="帖子数量")
    post_ids: list[int] = Field(default_factory=list, description="该日期对应的帖子ID列表，用于反向追溯")


class Freshness(CustomBaseModel):
    """数据新鲜度"""
    last_7_days: float = Field(0.0, description="最近7天帖子占比 (0-1)")
    last_30_days: float = Field(0.0, description="最近30天帖子占比 (0-1)")
    avg_age_days: float = Field(0.0, description="平均发布天数")


# ==================== 新增派生分析图表 Schema ====================

class IpaPoint(CustomBaseModel):
    """IPA 分析点"""
    name: str
    x: int = Field(..., description="声量 (关注度)")
    y: float = Field(..., description="情感 (满意度)")
    score: float = Field(..., description="综合评分")
    post_ids: list[int] = Field(default_factory=list)


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


class CompetitorRadar(CustomBaseModel):
    """竞品雷达分析"""
    mode: Literal["radar", "bar", "none"] = "none"
    dimensions: list[str] | None = None
    series: list[CompetitorSeries] = Field(default_factory=list)


class TaskAnalysisCharts(CustomBaseModel):
    """图表数据"""
    quadrant: list[QuadrantItem] = Field(default_factory=list, description="四象限数据")
    quadrant_summary: QuadrantSummary = Field(default_factory=QuadrantSummary, description="四象限统计")
    time_distribution: list[TimeDistributionItem] = Field(default_factory=list, description="时间分布")
    # 新增图表字段
    ipa_analysis: IpaAnalysis | None = None
    context_graph: ContextGraph | None = None
    competitor_radar: CompetitorRadar | None = None


class SourceDistribution(CustomBaseModel):
    """来源分布（帖子 vs 评论）"""
    post: float = Field(0.0, description="来自帖子的占比 (0-1)")
    comment: float = Field(0.0, description="来自评论的占比 (0-1)")


class SentimentDistribution(CustomBaseModel):
    """情感分布"""
    positive: int = Field(0, description="正面提及次数")
    negative: int = Field(0, description="负面提及次数")
    neutral: int = Field(0, description="中性提及次数")


class EntityNormalizedInfo(CustomBaseModel):
    """实体归一化信息"""
    aliases: list[str] = Field(default_factory=list)
    parent: str | None = None
    children: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)


class EntityStat(CustomBaseModel):
    """实体统计"""
    name: str = Field(..., description="实体名称")
    type: str = Field("其他", description="实体类型")
    role: str = Field("other", description="主体角色: target(本品)/competitor(竞品)/other(其他有价值实体)")
    heat: float = Field(0, description="热度（CII加权）")
    mentions: int = Field(0, description="唯一帖子提及数")
    sentiment: float = Field(0, description="派生情感值 [-1, 1]，CII加权")
    sentiment_distribution: SentimentDistribution = Field(default_factory=SentimentDistribution, description="情感分布")
    source_distribution: SourceDistribution = Field(default_factory=SourceDistribution, description="来源分布")
    top_features: list[str] = Field(default_factory=list, description="主要特性")
    top_issues: list[str] = Field(default_factory=list, description="主要问题")
    top_expectations: list[str] = Field(default_factory=list, description="主要期望")
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID，用于反向追溯")
    normalized_info: EntityNormalizedInfo | None = None


class OpinionStat(CustomBaseModel):
    """观点统计"""
    name: str = Field(..., description="话题/类别名称") # unified to name
    topic: str | None = None # legacy compatibility
    category: str | None = None
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="唯一帖子提及数")
    sentiment: float = Field(0, description="情感倾向")
    source_distribution: SourceDistribution = Field(default_factory=SourceDistribution, description="来源分布")
    top_opinions: list[str] | None = None  # legacy compatibility
    opinions: list[dict] | None = None # new structure: [{"text": "...", "count": 1}]
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID，用于反向追溯")
    # Add count fields
    post_source_count: int = 0
    comment_source_count: int = 0


# ==================== KANO 需求分层 Schema (§4.5.3) ====================

class KanoItem(CustomBaseModel):
    """KANO 模型单项"""
    name: str = Field(..., description="标签名称") # unified to name
    label: str | None = None # legacy
    score: float = Field(0, description="综合评分") # renamed from heat
    heat: float | None = None # legacy
    mentions: int = Field(0, description="提及数")
    sentiment: float = Field(0, description="情感倾向")
    source_type: str = "opinion"
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID，用于反向追溯")
    top_opinions: list[str] | None = None  # legacy


class KanoModel(CustomBaseModel):
    """KANO 需求分层模型"""
    must_be: list[KanoItem] = Field(default_factory=list, description="基本型需求（痛点）")
    attractive: list[KanoItem] = Field(default_factory=list, description="兴奋型需求（惊喜）")
    one_dimensional: list[KanoItem] = Field(default_factory=list, description="期望型需求（愿望）")


class Opportunities(CustomBaseModel):
    """机会洞察"""
    kano_model: KanoModel = Field(default_factory=KanoModel, description="KANO 需求分层")


# ==================== 场景与人群画像 Schema (§4.5.4) ====================

class ScenarioStat(CustomBaseModel):
    """场景统计"""
    label: str = Field(..., description="场景标签")
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="提及数")
    associated_issues: list[str] = Field(default_factory=list, description="关联问题")
    associated_features: list[str] = Field(default_factory=list, description="关联特性")
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID，用于反向追溯")


class AudienceStat(CustomBaseModel):
    """人群画像统计"""
    label: str = Field(..., description="人群标签")
    heat: float = Field(0, description="热度")
    mentions: int = Field(0, description="提及数")
    preferences: list[str] = Field(default_factory=list, description="偏好")
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID，用于反向追溯")


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
    post_ids: list[int] = Field(default_factory=list, description="关联帖子ID")
    top_features: list[str] = Field(default_factory=list, description="主要特性")
    top_issues: list[str] = Field(default_factory=list, description="主要问题")


class Competition(CustomBaseModel):
    """竞品分析"""
    top_competitors: list[str] = Field(default_factory=list, description="主要竞品")
    comparison_sentiment: float = Field(0, description="对比情感（正=本品更好）")
    target_sentiment: float = Field(0, description="本品情感")
    competitor_sentiment: float = Field(0, description="竞品情感")
    competitor_details: list[CompetitorDetail] = Field(default_factory=list, description="竞品详情")


# ==================== KOL 声音 Schema ====================

class KolVoice(CustomBaseModel):
    """KOL 声音"""
    author: str = Field(..., description="作者名称")
    sentiment: float = Field(0, description="情感倾向")
    summary: str = Field("", description="观点摘要")
    post_id: int = Field(..., description="帖子ID")
    cii: float = Field(0, description="互动指数")


# ==================== 洞察数据 Schema ====================

class TaskAnalysisInsights(CustomBaseModel):
    """洞察数据"""
    top_entities: list[EntityStat] = Field(default_factory=list, description="热门实体（全部）")
    target_entities: list[EntityStat] = Field(default_factory=list, description="本品实体")
    competitor_entities: list[EntityStat] = Field(default_factory=list, description="竞品实体")
    top_issues: list[OpinionStat] = Field(default_factory=list, description="热门问题（负面）")
    top_features: list[OpinionStat] = Field(default_factory=list, description="热门特性（正面）")
    # context_analysis: ContextAnalysis # 已废弃，数据移至 charts.context_graph
    opportunities: Opportunities = Field(default_factory=Opportunities, description="机会洞察")
    # competition: Competition # 已废弃，数据移至 charts.competitor_radar
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


# ==================== 帖子分析列表 Schema ====================

class PostAnalysisWithPostInfo(CustomBaseModel):
    """带帖子信息的分析结果"""
    # 帖子基本信息
    post_id: int
    post_id_on_platform: str | None = None  # 平台上的帖子ID，用于关联原文数据
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
    """帖子分析列表响应"""
    items: list[PostAnalysisWithPostInfo]
    total: int
    page: int
    page_size: int

