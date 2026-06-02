"""创意研究 Profile — Filter 节点规则"""

from src.research_agent.profiles.base import FilterRules

SYSTEM_PROMPT = """你是一个创意案例筛选专家。给定一组搜索结果和研究问题，请评估每条结果对创意研究的参考价值。

评分原则（按优先级）：
1. 【创意参考价值】文章是否包含可借鉴的创意做法、视觉/文案钩子、传播机制或品牌叙事——这是评分的决定性依据
2. 【案例具体性】有具体品牌/campaign 名称与执行细节的内容优于泛泛而谈的趋势漫谈
3. 【硬性上限】无论媒体多知名，若文章仅是行业新闻/公司公告/通稿而无创意拆解，评分不超过 0.35
4. 【媒体偏好】数英/TOPYS/广告门/梅花网/SocialBeta 等垂直创意媒体的案例文章更具参考价值；但来源本身不能替代内容判断

对每条结果打分（0-1），选出最相关的 {max_n} 条。

{strategy_hint}

输出 JSON 数组，每个元素包含：
- "index": 原始列表中的序号（从 0 开始）
- "score": 相关性评分（0-1）
- "reason": 一句话理由（说明这条能提供什么创意参考，或为何缺乏参考价值）

只输出 JSON 数组，按 score 降序排列，不要其他内容。"""


STRATEGY_HINT = (
    "辅助评分规则（在参考价值基础上叠加，不改变参考价值主导地位）：\n"
    "- 标题含具体品牌名 + campaign/案例/创意/营销等词的结果，加 0.10 分\n"
    "- 标题纯属新闻通稿/融资公告/人事变动/榜单排名类，减 0.15 分\n"
    "- 来源为垂直创意媒体（数英/TOPYS/广告门/梅花网/SocialBeta 等），加 0.05 分\n"
    "- 内容仅涉及无关品类（即使是知名媒体），不加分，并受 0.35 上限约束"
)


# 创意研究不需要"权威 tier"概念——所有来源都是编辑部内容，品质差异不体现在 tier 上。
# 保留 tier1/tier2 作为可选的"推荐程度"标签：核心垂直媒体进 tier1，辅助来源进 tier2。
TIER1_DOMAINS = frozenset(
    {
        "digitaling.com",  # 数英
        "topys.cn",  # TOPYS
        "adquan.com",  # 广告门
        "meihua.info",  # 梅花网
        "socialbeta.com",  # SocialBeta
        "campaignchina.com",  # Campaign 中国
    }
)


TIER2_DOMAINS = frozenset(
    {
        "adfame.cn",
        "adage.com",
        "campaignbrief.com",
        "dmunion.com",
        "xinpianchang.com",
        "36kr.com",  # 新消费品牌报道
    }
)


# 创意研究不需要过滤"服务页"模式——创意站没有这种页面。留空即可。
SERVICE_PAGE_PATTERNS: tuple[str, ...] = ()


# 创意内容主要是 HTML 文章，不需要 PDF 优先
CONTENT_TYPE_PRIORITY = ("html", "pdf")


# 创意场景下 LLM 评分分布更宽（创意价值主观性更强），阈值适当放宽
MIN_LLM_SCORE = 0.35


FILTER_RULES = FilterRules(
    system_prompt=SYSTEM_PROMPT,
    strategy_hint=STRATEGY_HINT,
    tier1_domains=TIER1_DOMAINS,
    tier2_domains=TIER2_DOMAINS,
    service_page_patterns=SERVICE_PAGE_PATTERNS,
    content_type_priority=CONTENT_TYPE_PRIORITY,
    min_llm_score=MIN_LLM_SCORE,
)
