"""LangGraph State 定义

Phase 1 使用线性图（plan → search → filter → synthesize），无循环。
documents/findings 使用 operator.add reducer 为 Phase 3 循环做准备。
"""

import operator
from typing import Annotated, TypedDict


class SearchPlan(TypedDict):
    keywords: list[str]
    target_domains: list[str]
    search_angles: list[str]


class Candidate(TypedDict):
    title: str
    url: str
    snippet: str
    source: str
    content_type: str
    source_tier: str  # "tier1" | "tier2" | "tier3"
    relevance_score: float
    published_date: str  # ISO date or year string, empty if unknown


class DataPoint(TypedDict):
    metric: str
    value: str
    period: str
    source: str


class Finding(TypedDict):
    source_url: str
    source_title: str
    source_tier: str
    published_date: str  # ISO date or year string, empty if unknown
    key_points: list[str]
    data_points: list[DataPoint]
    relevance_to_questions: dict[str, str]
    question_relevance_scores: dict[str, float]  # 每题实质相关度 0.0–1.0，Analyzer LLM 打分


class QuestionFinding(TypedDict):
    """按研究问题组织的发现（synthesize 节点产出）"""

    answer_summary: str
    confidence: str  # "high" | "medium" | "low"
    data_points: list[DataPoint]
    source_refs: list[str]


class Document(TypedDict):
    url: str
    title: str
    content: str
    source: str
    content_type: str
    page_count: int | None
    published_date: str  # ISO date or year string, empty if unknown


class Evaluation(TypedDict):
    questions_covered: list[str]
    gap_questions: list[str]
    tier1_source_count: int
    should_continue: bool


class ResearchState(TypedDict):
    # 输入
    query: str
    context: str  # 研究背景/补充说明（可选，planner 使用）
    title: str  # 研究标题（planner 自动生成）
    research_questions: list[str]
    profile_name: str  # 研究类型："industry" / "creative"，决定各节点使用的 prompt 与规则

    # 过程数据（每轮替换）
    search_plan: SearchPlan
    candidates: list[Candidate]
    selected: list[Candidate]

    # 跨轮次累积（reducer 注解）
    documents: Annotated[list[Document], operator.add]
    findings: Annotated[list[Finding], operator.add]

    # 评估（Phase 3 启用）
    evaluation: Evaluation

    # 控制
    round: int
    max_rounds: int

    # 输出（synthesize 节点填入）
    findings_by_question: dict[str, QuestionFinding]
    synthesis: str
    coverage: dict
    information_gaps: list[str]

    # Token 用量（各节点 LLM 调用后追加，tasks.py 汇总）
    token_usage_records: Annotated[list[dict], operator.add]
