"""Research Agent Pydantic 模型"""

from datetime import datetime

from pydantic import Field

from src.schemas import CustomBaseModel


class BriefExtractResult(CustomBaseModel):
    """文件提取的纯文本"""

    text: str


class ProfileOption(CustomBaseModel):
    """研究类型选项（供前端选择器展示）"""

    name: str = Field(..., description="profile 标识（industry / creative）")
    display_name: str = Field(..., description="展示名")


class ResearchPlanPreviewRequest(CustomBaseModel):
    """预览研究计划（不创建任务，仅调用 planner LLM）"""

    analysis_goal: str = Field(..., min_length=2, max_length=2000, description="核心研究意图（AI 提炼或用户手填）")
    brief: str | None = Field(default=None, max_length=5000, description="原始 Brief 文本（可选，供 planner 参考）")
    research_questions: list[str] | None = Field(default=None, description="初始研究问题（可选）")
    profile_name: str = Field(
        default="industry",
        description="研究类型：industry（行业研究）/ creative（创意研究）",
    )


class ResearchPlanPreviewResult(CustomBaseModel):
    """planner LLM 返回的研究计划预览"""

    title: str
    analysis_goal: str
    research_questions: list[str]
    keywords: list[str]
    search_angles: list[str]


class ResearchTaskCreate(CustomBaseModel):
    """创建研究任务"""

    analysis_goal: str = Field(..., min_length=2, max_length=2000, description="核心研究意图，贯穿整个研究链")
    title: str = Field(..., min_length=1, max_length=200, description="研究标题")
    brief: str | None = Field(
        default=None, max_length=5000, description="原始 Brief 文本（可选，作为 planner 背景参考）"
    )
    research_questions: list[str] | None = Field(
        default=None, description="研究问题列表（可选，plan 节点会自动生成）"
    )
    search_config: dict | None = Field(
        default=None, description="搜索配置：research_scope, focus_domains"
    )
    profile_name: str = Field(
        default="industry",
        description="研究类型：industry（行业研究）/ creative（创意研究）",
    )


class ResearchTaskRead(CustomBaseModel):
    """研究任务详情

    DB 列名为 query，对外 API 统一暴露为 analysis_goal（使用 alias 映射）。
    """

    id: int
    title: str | None = None
    analysis_goal: str
    research_questions: list[str] | None = None
    search_config: dict | None = None
    profile_name: str = "industry"
    strategy_id: int | None = None
    user_id: int
    job_id: int | None = None
    status: str
    error_message: str | None = None
    stats: dict | None = None
    progress: list | None = None
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
    published_date: str = ""


class CoverageSchema(CustomBaseModel):
    """覆盖度元信息"""

    questions_covered: int = 0
    questions_total: int = 0
    high_confidence_count: int = 0
    source_quality: dict = {}


class ResearchTaskResult(CustomBaseModel):
    """研究结果（完整结构化产出）"""

    id: int
    analysis_goal: str
    status: str
    findings_by_question: dict[str, QuestionFindingSchema] | None = None
    synthesis: str | None = None
    sources: list[SourceSchema] | None = None
    coverage: CoverageSchema | None = None
    information_gaps: list[str] | None = None
    stats: dict | None = None
