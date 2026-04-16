"""行业研究 Profile 拼装入口"""

from src.research_agent.profiles.base import ResearchProfile
from src.research_agent.profiles.industry.analyzer import ANALYZER_PROMPT
from src.research_agent.profiles.industry.fetcher import FETCHER_RULES
from src.research_agent.profiles.industry.filter import FILTER_RULES
from src.research_agent.profiles.industry.planner import PLANNER_CONTEXT
from src.research_agent.profiles.industry.synthesizer import SYNTHESIZER_PROMPT

# Tavily/Exa 兜底域名：所有行业研究都会合并到搜索范围内
# 原 settings.RESEARCH_AGENT_TARGET_DOMAINS 迁移到此处作为 industry 专属
SEARCH_FALLBACK_DOMAINS = (
    # 中国政府统计 —— 几乎所有中国市场研究都需要基础数据
    "stats.gov.cn",       # 国家统计局
    "ndrc.gov.cn",        # 国家发改委，产业政策/五年规划
    # 国际数据平台 —— 跨领域通用，提供跨国对标与宏观数据
    "oecd.org",           # 跨国行业对标与政策比较
    "ourworldindata.org", # 开放数据，13000+ 图表
    "pewresearch.org",    # 全球消费者/技术态度调查
    "datareportal.com",   # 全球数字消费者年度报告
    # 广域财经媒体 —— 覆盖面宽，适合多数商业研究主题
    "36kr.com",           # 科技/创投/数字经济
    "latepost.com",       # 深度商业调查报道
)


INDUSTRY_PROFILE = ResearchProfile(
    name="industry",
    display_name="行业研究",
    planner_context=PLANNER_CONTEXT,
    analyzer_prompt=ANALYZER_PROMPT,
    synthesizer_prompt=SYNTHESIZER_PROMPT,
    filter=FILTER_RULES,
    fetcher=FETCHER_RULES,
    search_fallback_domains=SEARCH_FALLBACK_DOMAINS,
)
