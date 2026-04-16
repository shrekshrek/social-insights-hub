"""ResearchProfile dataclass 定义

每种研究类型（industry / creative / ...）提供一份 profile，
包含所有节点需要的 prompt 与规则参数。节点只读 profile，不包含业务硬编码。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FilterRules:
    """Filter 节点的筛选规则"""

    system_prompt: str
    """Filter 节点 LLM system prompt 模板，必须包含 {max_n} 与 {strategy_hint} 占位符"""

    strategy_hint: str
    """辅助评分规则文本（取代旧版 _build_report_hint 的前半部分）"""

    tier1_domains: frozenset[str]
    """一级权威来源域名（对筛选无直接影响，仅作为 sources 展示的 tier 标注）"""

    tier2_domains: frozenset[str]
    """二级行业机构来源域名"""

    service_page_patterns: tuple[str, ...]
    """URL 路径片段，命中即视为非研究内容的"服务/营销介绍页"，会被降序置后"""

    content_type_priority: tuple[str, ...]
    """content_type 优先级排序，列表靠前优先级高（candidate 列表 sort key）"""

    min_llm_score: float
    """LLM 相关性评分阈值，低于此分直接丢弃不进入后续打分"""


@dataclass(frozen=True)
class FetcherRules:
    """Fetcher 节点的抓取规则"""

    download_indicators: tuple[str, ...]
    """介绍页判断关键词：HTML 内容含有这些词时尝试提取 PDF 链接（空元组 = 禁用）"""

    landing_page_max_len: int
    """介绍页长度上限：HTML 内容超过此长度视为正文，不再尝试 PDF 提取"""

    max_content_len: int
    """单文档内容截断上限，传入 analyzer 前生效"""

    enable_pdf_extract: bool
    """是否启用"HTML 介绍页 → 提取 PDF 链接 → 下载 PDF 全文"的降级逻辑"""


@dataclass(frozen=True)
class ResearchProfile:
    """完整研究 profile

    - name / display_name: profile 标识与展示名
    - planner_context: 注入 PLAN_SYSTEM_TEMPLATE 的 {planner_context} 占位
    - analyzer_prompt: Analyzer 节点 LLM system prompt（完整字符串）
    - synthesizer_prompt: Synthesizer 节点 LLM system prompt（完整字符串）
    - filter / fetcher: 节点级规则集（见上）
    - search_fallback_domains: Searcher 节点合并到每次搜索的兜底域名。
      LLM planner 输出的 target_domains 会与此列表合并去重后作为 Tavily/Exa 的 include_domains。
      空元组表示完全依赖 planner LLM 自主挑选域名。
    """

    name: str
    display_name: str
    planner_context: str
    analyzer_prompt: str
    synthesizer_prompt: str
    filter: FilterRules
    fetcher: FetcherRules
    search_fallback_domains: tuple[str, ...] = ()
