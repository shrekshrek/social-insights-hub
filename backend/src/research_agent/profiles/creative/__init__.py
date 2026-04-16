"""创意研究 Profile 拼装入口"""

from src.research_agent.profiles.base import ResearchProfile
from src.research_agent.profiles.creative.analyzer import ANALYZER_PROMPT
from src.research_agent.profiles.creative.fetcher import FETCHER_RULES
from src.research_agent.profiles.creative.filter import FILTER_RULES
from src.research_agent.profiles.creative.planner import PLANNER_CONTEXT
from src.research_agent.profiles.creative.synthesizer import SYNTHESIZER_PROMPT

# Tavily/Exa 兜底域名：创意研究的核心垂直媒体
# 每次创意搜索都会合并这些域名，保证创意内容的基础覆盖面
SEARCH_FALLBACK_DOMAINS = (
    "digitaling.com",     # 数英，创意/营销案例
    "topys.cn",           # TOPYS，创意内容与品牌叙事
    "adquan.com",         # 广告门，案例与创意评析
    "socialbeta.com",     # SocialBeta，品牌营销观察
    "meihua.info",        # 梅花网，创意作品库
)


CREATIVE_PROFILE = ResearchProfile(
    name="creative",
    display_name="创意研究",
    planner_context=PLANNER_CONTEXT,
    analyzer_prompt=ANALYZER_PROMPT,
    synthesizer_prompt=SYNTHESIZER_PROMPT,
    filter=FILTER_RULES,
    fetcher=FETCHER_RULES,
    search_fallback_domains=SEARCH_FALLBACK_DOMAINS,
)
