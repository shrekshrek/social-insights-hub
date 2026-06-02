"""行业研究 Profile — Filter 节点规则"""

from src.research_agent.profiles.base import FilterRules

SYSTEM_PROMPT = """你是一个研究文献筛选专家。给定一组搜索结果和研究问题，请评估每条结果的相关性。

评分原则（按优先级）：
1. 【内容相关性】文章实质内容是否直接回答研究问题——这是评分的决定性依据
2. 【来源权威性】权威机构来源仅在内容相关度相近时作为优先选择依据，不能替代内容相关性
3. 【硬性上限】无论来源多权威，若文章内容与研究问题无直接关联（如咨询公司发布的无关行业报告），评分不超过 0.35

对每条结果打分（0-1），选出最相关的 {max_n} 条。

{strategy_hint}

输出 JSON 数组，每个元素包含：
- "index": 原始列表中的序号（从 0 开始）
- "score": 相关性评分（0-1）
- "reason": 一句话理由（说明内容与研究问题的关联，或说明为何内容不相关）

只输出 JSON 数组，按 score 降序排列，不要其他内容。"""


STRATEGY_HINT = (
    "辅助评分规则（在内容相关性基础上叠加，不改变相关性主导地位）：\n"
    '- URL 以 .pdf 结尾或标题含"报告""白皮书""研究""report"等词的结果，加 0.10 分\n'
    '- 候选列表中标注了"[服务介绍页，非报告]"的结果，减 0.20 分\n'
    "- 内容仅涉及无关行业/主题（即使来源权威），不加分，并受 0.35 上限约束"
)


TIER1_DOMAINS = frozenset(
    {
        # 综合咨询/四大（子域名由父域名 `in` 匹配自动覆盖，无需单独列出）
        "mckinsey.com",
        "mckinsey.com.cn",  # 不同 TLD，均需保留
        "deloitte.com",
        "pwccn.com",
        "pwc.com",  # 不同域名，均需保留
        "ey.com",
        "kpmg.com",
        "bcg.com",
        "bain.com",
        "rolandberger.com",
        "accenture.com",
        "oliverwyman.com",
        "kearney.com",
        # 中国政府/权威机构
        "cssn.cn",
        "drc.gov.cn",
        "stats.gov.cn",
        "cnnic.net.cn",
        "miit.gov.cn",
        "mofcom.gov.cn",
        "pbc.gov.cn",
        "ndrc.gov.cn",
        "csrc.gov.cn",
        # 上市公司披露平台（含付费级行业数据）
        "cninfo.com.cn",
        "hkexnews.hk",
        "sse.com.cn",
        # 国际权威机构（worldbank.org 覆盖 documents/openknowledge 等所有子域名）
        "oecd.org",
        "unctad.org",
        "worldbank.org",
        "imf.org",
        "wto.org",
        "adb.org",
    }
)


TIER2_DOMAINS = frozenset(
    {
        # 中国行业研究机构（子域名由父域名 `in` 匹配自动覆盖）
        "iresearch.cn",
        "questmobile.com.cn",
        "caict.ac.cn",
        "cesi.cn",
        "aliresearch.com",
        "mob.com",
        "research.hktdc.com",
        # B2B 买方行为研究（发布完整免费报告）
        "edelman.com",
        "linkedin.com",  # 覆盖 business.linkedin.com 等所有子域名
        "datareportal.com",
        "pewresearch.org",
        "ourworldindata.org",
        # 企业服务研究（如搜索到摘要页仍有参考价值）
        "gartner.com",
        "forrester.com",
        # 垂直媒体/深度报道
        "36kr.com",
        "latepost.com",
        "caam.org.cn",
        "ccfa.org.cn",
    }
)


# 咨询公司自有营销/服务页面的 URL 路径模式（代码层直接标记，比 prompt 规则更可靠）
SERVICE_PAGE_PATTERNS = (
    "/services/",
    "/service/",
    "/about/",
    "/careers/",
    "/awards/",
    "/our-work/",
    "/industries/",
    "/solutions/",
    "/capabilities/",
    "/who-we-are/",
    "/join-us/",
)


# 报告研究模式：PDF 优先，HTML 次之
CONTENT_TYPE_PRIORITY = ("pdf", "html")


# LLM 基础分最低入选阈值：低于此分数的候选直接丢弃
MIN_LLM_SCORE = 0.40


FILTER_RULES = FilterRules(
    system_prompt=SYSTEM_PROMPT,
    strategy_hint=STRATEGY_HINT,
    tier1_domains=TIER1_DOMAINS,
    tier2_domains=TIER2_DOMAINS,
    service_page_patterns=SERVICE_PAGE_PATTERNS,
    content_type_priority=CONTENT_TYPE_PRIORITY,
    min_llm_score=MIN_LLM_SCORE,
)
