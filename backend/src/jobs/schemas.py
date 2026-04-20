"""跨渠道 AnalysisJob Pydantic schemas。

Token 使用统计 + AnalysisJob 增删改查 + 进度查询的响应模型。
所有渠道共用，analysis/news_media/strategies 等模块可以从 src.jobs.schemas import。
"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel, PaginatedResponse


# ==================== Token 使用统计 ====================


class CallDetail(CustomBaseModel):
    """单次 LLM 调用详情"""

    call_index: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_cny: float
    duration_seconds: float
    timestamp: datetime | None = None
    # DeepSeek Context Caching 字段（旧记录无此字段时默认 0）
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0


class TokenUsageSummary(CustomBaseModel):
    """Token 使用汇总"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_cny: float = 0.0
    total_duration_seconds: float = 0.0
    avg_tokens_per_call: float = 0.0
    avg_cost_per_call: float = 0.0
    # DeepSeek Context Caching 字段（旧记录无此字段时默认 0）
    total_cache_hit_tokens: int = 0
    total_cache_miss_tokens: int = 0
    cache_hit_ratio: float = 0.0


class TokenUsageStats(CustomBaseModel):
    """Token 使用统计"""

    summary: TokenUsageSummary = Field(default_factory=TokenUsageSummary)
    call_details: list[CallDetail] = []


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


class AnalysisJobListResponse(PaginatedResponse[AnalysisJobResponse]):
    """分析任务列表响应"""


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
