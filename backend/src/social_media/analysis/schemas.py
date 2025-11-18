"""分析模块Pydantic模型"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator

from src.schemas import CustomBaseModel


# ==================== Token Usage Schemas ====================

class CallDetail(CustomBaseModel):
    """单次LLM调用详情"""
    call_index: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_cny: float
    duration_seconds: float
    timestamp: Optional[str] = None


class TokenUsageSummary(CustomBaseModel):
    """Token使用摘要"""
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_cny: float
    total_duration_seconds: float
    avg_tokens_per_call: float
    avg_cost_per_call: float


class TokenUsageStats(CustomBaseModel):
    """Token使用统计"""
    summary: TokenUsageSummary
    call_details: List[CallDetail] = []


# ==================== Post Analysis Schemas ====================

class PostAnalysisCreate(CustomBaseModel):
    """创建帖子分析"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_id: int = Field(..., gt=0, description="帖子ID")
    spam_score: Optional[float] = Field(None, ge=0, le=10, description="垃圾分(0-10)")
    value_score: Optional[float] = Field(None, ge=0, le=10, description="价值分(0-10)")
    relevance_score: Optional[float] = Field(None, ge=0, le=10, description="相关度分(0-10)")
    sentiment: Optional[int] = Field(None, ge=-1, le=1, description="情感倾向(-1/0/1)")
    depth_analysis_result: Optional[Dict[str, Any]] = Field(None, description="深度分析结果")


class PostAnalysisResponse(CustomBaseModel):
    """帖子分析响应"""
    id: int
    task_id: int
    post_id: int
    spam_score: Optional[float]
    value_score: Optional[float]
    relevance_score: Optional[float]
    sentiment: Optional[int]
    depth_analysis_result: Optional[Dict[str, Any]]
    analyzed_at: Optional[datetime]
    analysis_model: Optional[str]
    created_at: datetime
    updated_at: datetime


# ==================== Comment Analysis Schemas ====================

class CommentAnalysisCreate(CustomBaseModel):
    """创建评论分析"""
    task_id: int = Field(..., gt=0, description="任务ID")
    comment_id: int = Field(..., gt=0, description="评论ID")
    spam_score: Optional[float] = Field(None, ge=0, le=10)
    value_score: Optional[float] = Field(None, ge=0, le=10)
    relevance_score: Optional[float] = Field(None, ge=0, le=10)
    sentiment: Optional[int] = Field(None, ge=-1, le=1)
    depth_analysis_result: Optional[Dict[str, Any]] = None


class CommentAnalysisResponse(CustomBaseModel):
    """评论分析响应"""
    id: int
    task_id: int
    comment_id: int
    spam_score: Optional[float]
    value_score: Optional[float]
    relevance_score: Optional[float]
    sentiment: Optional[int]
    depth_analysis_result: Optional[Dict[str, Any]]
    analyzed_at: Optional[datetime]
    analysis_model: Optional[str]
    created_at: datetime
    updated_at: datetime


# ==================== Task Analysis Result Schemas ====================

class TaskAnalysisResultCreate(CustomBaseModel):
    """创建任务分析结果"""
    task_id: int = Field(..., gt=0, description="任务ID")
    analysis_type: str = Field(
        ...,
        pattern="^(screening_posts|screening_comments|deep_posts|deep_comments)$",
        description="分析类型"
    )
    celery_task_id: str = Field(..., description="Celery任务ID")
    source_count: int = Field(0, ge=0, description="源数据数量")


class TaskAnalysisResultResponse(CustomBaseModel):
    """任务分析结果响应"""
    id: int
    task_id: int
    analysis_type: str
    result_data: Optional[Dict[str, Any]]
    analysis_summary: Optional[str]
    source_count: int
    analyzed_count: int
    failed_count: int
    celery_task_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    processing_time: Optional[int]
    token_usage: Optional[TokenUsageStats]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskAnalysisResultListResponse(CustomBaseModel):
    """任务分析结果列表响应"""
    items: List[TaskAnalysisResultResponse]
    total: int
    page: int
    page_size: int


# ==================== Project Analysis Result Schemas ====================

class ProjectAnalysisResultCreate(CustomBaseModel):
    """创建项目分析结果"""
    project_id: int = Field(..., gt=0, description="项目ID")
    analysis_type: str = Field(
        ...,
        pattern="^(topic_clustering|competitive_analysis)$",
        description="分析类型"
    )
    analysis_config: Optional[Dict[str, Any]] = Field(None, description="分析配置")
    source_task_ids: Optional[List[int]] = Field(None, description="源任务ID列表")


class ProjectAnalysisResultResponse(CustomBaseModel):
    """项目分析结果响应"""
    id: int
    project_id: int
    user_id: int
    analysis_type: str
    analysis_config: Optional[Dict[str, Any]]
    source_task_ids: Optional[List[int]]
    source_data_count: int
    result_data: Optional[Dict[str, Any]]
    analysis_summary: Optional[str]
    celery_task_id: str
    status: str
    processing_time: Optional[int]
    token_usage: Optional[TokenUsageStats]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    updated_at: datetime


class ProjectAnalysisResultListResponse(CustomBaseModel):
    """项目分析结果列表响应"""
    items: List[ProjectAnalysisResultResponse]
    total: int
    page: int
    page_size: int


# ==================== Analysis Request Schemas ====================

class RunScreeningRequest(CustomBaseModel):
    """运行初筛分析请求"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: Optional[List[int]] = Field(None, description="指定帖子ID列表")
    comment_ids: Optional[List[int]] = Field(None, description="指定评论ID列表")
    analyze_all: bool = Field(False, description="分析所有数据")

    @field_validator('analyze_all')
    @classmethod
    def validate_analyze_all(cls, v, info):
        """验证至少指定一种分析对象"""
        post_ids = info.data.get('post_ids')
        comment_ids = info.data.get('comment_ids')
        if not v and not post_ids and not comment_ids:
            raise ValueError("必须指定post_ids、comment_ids或设置analyze_all=True")
        return v


class RunDeepAnalysisRequest(CustomBaseModel):
    """运行深度分析请求"""
    task_id: int = Field(..., gt=0, description="任务ID")
    post_ids: Optional[List[int]] = Field(None, description="指定帖子ID列表")
    comment_ids: Optional[List[int]] = Field(None, description="指定评论ID列表")
    analysis_focus: Optional[List[str]] = Field(
        None,
        description="分析重点（如：用户画像、需求挖掘、竞品分析等）"
    )


class RunClusteringRequest(CustomBaseModel):
    """运行聚类分析请求"""
    project_id: int = Field(..., gt=0, description="项目ID")
    task_ids: Optional[List[int]] = Field(None, description="指定任务ID列表")
    num_clusters: int = Field(5, ge=2, le=20, description="聚类数量")
    clustering_method: str = Field(
        "kmeans",
        pattern="^(kmeans|hierarchical|dbscan)$",
        description="聚类方法"
    )


class RunCompetitiveRequest(CustomBaseModel):
    """运行竞品分析请求"""
    project_id: int = Field(..., gt=0, description="项目ID")
    task_ids: Optional[List[int]] = Field(None, description="指定任务ID列表")
    competitor_keywords: List[str] = Field(..., min_length=1, description="竞品关键词")
    comparison_metrics: Optional[List[str]] = Field(
        None,
        description="对比维度（如：功能、价格、用户评价等）"
    )


# ==================== Analysis Response Schemas ====================

class RunAnalysisResponse(CustomBaseModel):
    """运行分析响应"""
    celery_task_id: str = Field(..., description="Celery任务ID")
    result_id: int = Field(..., description="分析结果记录ID")
    status: str = Field(..., description="任务状态")
    message: str = Field(..., description="提示信息")


class AnalysisProgressResponse(CustomBaseModel):
    """分析进度响应"""
    result_id: int
    status: str
    progress: float = Field(..., ge=0, le=100, description="进度百分比")
    analyzed_count: int
    total_count: int
    estimated_time_remaining: Optional[int] = Field(None, description="预计剩余时间（秒）")
    current_cost: float
    current_tokens: int


# ==================== Statistics Schemas ====================

class AnalysisStatsResponse(CustomBaseModel):
    """分析统计响应"""
    total_tasks: int = Field(..., description="总任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    failed_tasks: int = Field(..., description="失败任务数")
    pending_tasks: int = Field(..., description="待处理任务数")
    processing_tasks: int = Field(..., description="处理中任务数")
    total_cost_cny: float = Field(..., description="总成本（人民币）")
    total_tokens: int = Field(..., description="总Token数")
    avg_processing_time: float = Field(..., description="平均处理时间（秒）")


class TaskAnalysisStatsResponse(CustomBaseModel):
    """任务级分析统计"""
    task_id: int
    task_name: str
    total_analyses: int
    screening_count: int
    deep_analysis_count: int
    total_cost: float
    total_tokens: int
    last_analysis_at: Optional[datetime]


class ProjectAnalysisStatsResponse(CustomBaseModel):
    """项目级分析统计"""
    project_id: int
    project_name: str
    total_analyses: int
    clustering_count: int
    competitive_count: int
    total_cost: float
    total_tokens: int
    last_analysis_at: Optional[datetime]
