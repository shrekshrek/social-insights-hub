"""Research Agent Pydantic 模型"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from pydantic import Field

from src.schemas import CustomBaseModel

if TYPE_CHECKING:
    from src.research_agent.models import ResearchTask


class ProfileOption(CustomBaseModel):
    """研究类型选项（供前端选择器展示）"""

    name: str = Field(..., description="profile 标识（industry / creative）")
    display_name: str = Field(..., description="展示名")


class ParseBriefTextRequest(CustomBaseModel):
    """文本入口的 brief 解析请求"""

    text: str = Field(
        ..., min_length=2, max_length=10000, description="待解析的 brief 文本"
    )
    profile_name: str = Field(
        default="industry",
        description="研究类型：industry（行业研究）/ creative（创意研究）",
    )


class ParseBriefResponse(CustomBaseModel):
    """brief 解析合流点的统一返回（摄入 + 诊断 + 方案）"""

    title: str
    analysis_goal: str
    research_questions: list[str]
    keywords: list[str]
    search_angles: list[str]
    verdict: str = Field(
        default="suitable",
        description="brief 与专题研究入口的适配度：suitable / partial / not_suitable",
    )
    recommended_profile: str = Field(
        default="",
        description="suitable 时给出的建议研究类型（industry / creative）；其他情况为空",
    )
    redirect_hint: str = Field(
        default="",
        description="not_suitable 时给出的应跳转入口（strategy / monitor_social / monitor_news）；其他情况为空",
    )
    note: str = Field(
        default="",
        description="判断依据（1-2 句中文，呈现给用户）",
    )
    brief_text: str = Field(
        default="",
        description="本次解析所用的原始 brief 文本（文件入口为抽取后的纯文本），用于任务创建时回传 search_config.context 与 profile 切换重解析",
    )


class ResearchTaskCreate(CustomBaseModel):
    """创建研究任务"""

    analysis_goal: str = Field(..., min_length=2, max_length=2000, description="核心研究意图，贯穿整个研究链")
    title: str = Field(..., min_length=1, max_length=200, description="研究标题")
    brief: str | None = Field(
        default=None, max_length=10000, description="原始 Brief 文本（可选，作为 planner 背景参考）"
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
    participant_ids: List[int] = Field(
        default_factory=list, description="参与者ID列表"
    )
    participant_usernames: List[str] = Field(
        default_factory=list, description="参与者用户名列表"
    )
    owner_username: str = Field(default="", description="创建者用户名")

    @classmethod
    def from_orm_full(cls, task: "ResearchTask") -> "ResearchTaskRead":
        """从 ORM ResearchTask 构造，附带 participants / owner 展示信息。"""
        return cls(
            id=task.id,
            title=task.title,
            analysis_goal=task.analysis_goal,
            research_questions=task.research_questions,
            search_config=task.search_config,
            profile_name=task.profile_name,
            strategy_id=task.strategy_id,
            user_id=task.user_id,
            job_id=task.job_id,
            status=task.status,
            error_message=task.error_message,
            stats=task.stats,
            progress=task.progress,
            created_at=task.created_at,
            updated_at=task.updated_at,
            participant_ids=[p.id for p in task.participants],
            participant_usernames=[p.username for p in task.participants],
            owner_username=task.user.username if task.user else "",
        )


class ResearchTaskUpdate(CustomBaseModel):
    """更新研究任务（仅允许编辑 title；其他字段改动会让既有研究结果失效，不予支持）"""

    title: str | None = Field(
        None, min_length=1, max_length=200, description="研究标题"
    )


class ResearchTaskParticipantAssignment(CustomBaseModel):
    """研究任务-参与者关联请求"""

    user_ids: List[int] = Field(
        ..., min_length=1, description="要添加的参与者用户ID列表"
    )


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
