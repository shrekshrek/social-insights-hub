"""Research Agent Pydantic 模型"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class ResearchTaskCreate(CustomBaseModel):
    """创建研究任务"""

    query: str = Field(..., min_length=2, max_length=500, description="研究主题")
    research_questions: list[str] | None = Field(
        default=None, description="研究问题列表（可选，plan 节点会自动生成）"
    )
    research_type: str = Field(
        default="industry_research",
        description="研究类型：industry_research（行业报告）| ad_campaign（广告营销）| product_research（产品设计）",
    )
    search_config: dict | None = Field(
        default=None, description="搜索配置：research_scope, focus_domains"
    )


class ResearchTaskRead(CustomBaseModel):
    """研究任务详情"""

    id: int
    query: str
    research_questions: list[str] | None = None
    search_config: dict | None = None
    strategy_id: int | None = None
    user_id: int
    job_id: int | None = None
    status: str
    error_message: str | None = None
    stats: dict | None = None
    created_at: datetime
    updated_at: datetime


class DataPointSchema(CustomBaseModel):
    """结构化数据点"""

    metric: str
    value: str
    period: str = ""
    source: str = ""


class QuestionFindingSchema(CustomBaseModel):
    """按研究问题组织的发现"""

    answer_summary: str
    confidence: str  # "high" | "medium" | "low"
    data_points: list[DataPointSchema] = []
    source_refs: list[str] = []


class SourceSchema(CustomBaseModel):
    """来源信息"""

    id: str
    title: str
    url: str
    source: str = ""
    source_tier: str = "tier3"
    content_type: str = "html"
    relevance_score: float = 0.0


class CoverageSchema(CustomBaseModel):
    """覆盖度元信息"""

    questions_covered: int = 0
    questions_total: int = 0
    high_confidence_count: int = 0
    source_quality: dict = {}


class ResearchTaskResult(CustomBaseModel):
    """研究结果（完整结构化产出）"""

    id: int
    query: str
    status: str
    findings_by_question: dict[str, QuestionFindingSchema] | None = None
    synthesis: str | None = None
    sources: list[SourceSchema] | None = None
    coverage: CoverageSchema | None = None
    information_gaps: list[str] | None = None
    stats: dict | None = None
