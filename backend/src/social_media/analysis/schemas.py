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
    type: Literal["品牌", "商品", "服务", "其他"] = Field(..., description="实体类型")
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
    sentiment: int | None = Field(None, ge=-1, le=1)
    post_deep_result: dict | None = None
    comment_deep_result: dict | None = None


class PostAnalysisUpdate(CustomBaseModel):
    """更新帖子分析"""
    spam_score: float | None = Field(None, ge=0, le=10)
    value_score: float | None = Field(None, ge=0, le=10)
    relevance_score: float | None = Field(None, ge=0, le=10)
    sentiment: int | None = Field(None, ge=-1, le=1)
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


# ==================== 向后兼容别名 ====================
# 删除旧的向后兼容别名，它们在文件末尾会被删除


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
    published_at: datetime | None = None
    url: str | None = None

    # 初筛分析
    spam_score: float | None = None
    value_score: float | None = None
    relevance_score: float | None = None
    sentiment: int | None = None

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


