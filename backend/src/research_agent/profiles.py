"""研究类型 Profile 定义

不同的 research_type 决定：搜索哪些域名、用什么视角分析、提取什么字段。
LangGraph 流程不变，Profile 参数化节点行为。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResearchProfile:
    """研究类型配置"""

    name: str
    description: str
    # 内容获取策略: "report"=优先查找/下载 PDF 报告, "article"=网页文章即可
    content_strategy: str = "article"
    # 定向搜索域名（与 config 默认域名合并）
    target_domains: list[str] = field(default_factory=list)
    # planner prompt：指导 LLM 规划搜索策略
    planner_context: str = ""
    # analyzer prompt：指导 LLM 从文档中提取什么
    analyzer_prompt: str = ""
    # synthesizer prompt：指导 LLM 如何综合分析
    synthesizer_prompt: str = ""


# ── 行业研究（默认）──────────────────────────────────────────

INDUSTRY_RESEARCH = ResearchProfile(
    name="industry_research",
    description="行业报告研究：市场格局、竞争分析、趋势预测",
    content_strategy="report",
    target_domains=[],  # 使用 config 默认域名
    planner_context="""⚠️ 重要：本次搜索的目标是找到可下载的专业研究报告（PDF/白皮书），而非普通网页文章。

关键词生成规则：
- 每个关键词必须包含"报告""白皮书""研究报告""PDF"等报告类修饰词
- 示例："2024新能源汽车行业报告 PDF"、"中国消费市场白皮书"、"XX行业研究报告"
- 同时生成中英文关键词：如 "China EV market report 2024"

可选的目标域名参考（不限于此，请根据主题补充更多）：

综合咨询/四大：
- mckinsey.com.cn / mckinsey.com（麦肯锡）
- deloitte.com（德勤）
- pwccn.com（普华永道）
- ey.com（安永）
- kpmg.com（毕马威）
- bcg.com（波士顿咨询）
- bain.com（贝恩）
- rolandberger.com（罗兰贝格）
- accenture.com（埃森哲）

政府/智库：
- cssn.cn（社科院）
- drc.gov.cn（国研中心）
- stats.gov.cn（国家统计局）

行业研究：
- iresearch.cn（艾瑞咨询）
- questmobile.com.cn（QuestMobile）
- euromonitor.com（欧睿国际）
- frost.com（弗若斯特沙利文）
- cbndata.com（CBNData）

请根据具体研究主题，补充该领域特有的权威机构域名。""",
    analyzer_prompt="""你是一个行业研究分析师。给定一篇文档全文和研究问题，请深度阅读并提取结构化信息。

输出 JSON 对象：
{
    "key_points": ["核心观点1", "核心观点2", ...],
    "data_points": [
        {"metric": "指标名", "value": "数值", "period": "时间范围", "source": "来源名"}
    ],
    "relevance_to_questions": {
        "研究问题1": "该文档对此问题的相关发现摘要（2-3句话）",
        "研究问题2": "无直接相关"
    }
}

重点提取：
- 具体数字、百分比、排名、市场规模等量化数据
- 趋势判断、竞争格局、技术路线等定性结论
- 预测和展望性数据

只输出 JSON，不要其他内容。""",
    synthesizer_prompt="""你是一个资深行业研究分析师。基于搜索结果，针对每个研究问题进行结构化分析。

你需要输出一个 JSON 对象，包含：

1. "findings_by_question": 按研究问题组织的发现
   每个问题包含：
   - "answer_summary": 简要回答（2-3 句话）
   - "confidence": "high"（多个权威源交叉验证）/ "medium"（有来源但不够充分）/ "low"（几乎无相关发现）
   - "data_points": 提取的具体数据 [{"metric": "指标", "value": "数值", "period": "时间范围", "source": "来源名"}]
   - "source_refs": 支撑该发现的来源 ID 列表（如 ["src_0", "src_1"]）

2. "synthesis": 完整的 Markdown 综合报告（按研究问题分章节，引用来源）

3. "information_gaps": 信息缺口列表（哪些问题数据不足，建议补充方向）

输出纯 JSON，不要 markdown 代码块包裹。""",
)


# ── 广告营销案例研究 ──────────────────────────────────────────

AD_CAMPAIGN_RESEARCH = ResearchProfile(
    name="ad_campaign",
    description="广告营销案例研究：创意策略、传播手法、营销效果",
    target_domains=[
        "digitaling.com",      # 数英网
        "meihua.info",         # 梅花网
        "socialbeta.com",      # SocialBeta
        "adquan.com",          # 广告门
        "topys.cn",            # TOPYS 创意平台
        "campaignasia.com",    # Campaign Asia
        "adweek.com",          # Adweek
        "thedrum.com",         # The Drum
        "adforum.com",         # AdForum
        "shots.net",           # shots
        "cannes-lions.cn",     # 戛纳创意节中文
    ],
    planner_context="""你要搜索的是广告营销行业网站，目标是找到品牌广告案例、营销活动分析、创意策略拆解。

可选的目标域名参考（不限于此，请根据品牌/行业补充）：

中文广告营销：
- digitaling.com（数英网 — 最全的中文广告案例库）
- meihua.info（梅花网 — 营销案例与行业洞察）
- socialbeta.com（SocialBeta — 社交营销案例）
- adquan.com（广告门 — 广告创意资讯）
- topys.cn（TOPYS — 全球创意案例）

国际广告营销：
- campaignasia.com（Campaign Asia）
- adweek.com（Adweek）
- thedrum.com（The Drum）

请根据具体品牌和行业，补充相关的营销垂直网站。""",
    analyzer_prompt="""你是一个资深广告营销分析师。给定一篇广告案例或营销分析文章，请深度阅读并提取结构化信息。

输出 JSON 对象：
{
    "key_points": ["核心创意洞察1", "营销策略要点2", ...],
    "data_points": [
        {"metric": "指标名", "value": "数值/描述", "period": "时间范围", "source": "来源名"}
    ],
    "relevance_to_questions": {
        "研究问题1": "该文章对此问题的相关发现摘要（2-3句话）",
        "研究问题2": "无直接相关"
    }
}

重点提取：
- 品牌/产品背景与营销目标
- 创意策略（Big Idea、核心洞察、传播主题）
- 媒介组合与投放策略
- 传播效果数据（曝光量、互动量、转化率、获奖情况等）
- 目标受众与消费者洞察
- 可复用的营销方法论

只输出 JSON，不要其他内容。""",
    synthesizer_prompt="""你是一个资深广告营销策略分析师。基于搜索到的广告案例和营销分析，针对每个研究问题进行结构化分析。

你需要输出一个 JSON 对象，包含：

1. "findings_by_question": 按研究问题组织的发现
   每个问题包含：
   - "answer_summary": 简要回答（2-3 句话）
   - "confidence": "high" / "medium" / "low"
   - "data_points": 提取的具体数据 [{"metric": "指标", "value": "数值", "period": "时间范围", "source": "来源名"}]
   - "source_refs": 支撑该发现的来源 ID 列表

2. "synthesis": 完整的 Markdown 综合报告（按研究问题分章节，重点分析创意策略、传播手法和效果）

3. "information_gaps": 信息缺口列表

输出纯 JSON，不要 markdown 代码块包裹。""",
)


# ── 产品设计研究 ──────────────────────────────────────────

PRODUCT_RESEARCH = ResearchProfile(
    name="product_research",
    description="产品设计研究：产品策略、用户体验、功能分析",
    target_domains=[
        "woshipm.com",         # 人人都是产品经理
        "pmcaff.com",          # PMCAFF
        "uxren.cn",            # UXRen
        "uxpa.org",            # UXPA
        "nngroup.com",         # Nielsen Norman Group
        "smashingmagazine.com",
        "medium.com",
        "producthunt.com",
    ],
    planner_context="""你要搜索的是产品设计行业网站，目标是找到产品分析、用户体验研究、功能拆解。

可选的目标域名参考：

中文产品社区：
- woshipm.com（人人都是产品经理 — 产品分析文章）
- pmcaff.com（PMCAFF — 产品经理社区）
- uxren.cn（UXRen — 用户体验研究）

国际产品/UX：
- nngroup.com（Nielsen Norman Group — UX 研究权威）
- smashingmagazine.com（Web/UX 设计）

请根据具体产品领域补充相关网站。""",
    analyzer_prompt="""你是一个资深产品分析师。给定一篇产品分析或用户体验研究文章，请深度阅读并提取结构化信息。

输出 JSON 对象：
{
    "key_points": ["产品策略要点1", "用户体验发现2", ...],
    "data_points": [
        {"metric": "指标名", "value": "数值/描述", "period": "时间范围", "source": "来源名"}
    ],
    "relevance_to_questions": {
        "研究问题1": "该文章对此问题的相关发现摘要（2-3句话）",
        "研究问题2": "无直接相关"
    }
}

重点提取：
- 产品定位与目标用户
- 核心功能设计与用户流程
- 用户数据（DAU/MAU、留存率、转化率等）
- 竞品对比分析
- 交互设计亮点与痛点
- 商业模式与变现策略

只输出 JSON，不要其他内容。""",
    synthesizer_prompt="""你是一个资深产品策略分析师。基于搜索到的产品分析和研究文章，针对每个研究问题进行结构化分析。

你需要输出一个 JSON 对象，包含：

1. "findings_by_question": 按研究问题组织的发现
   每个问题包含：
   - "answer_summary": 简要回答（2-3 句话）
   - "confidence": "high" / "medium" / "low"
   - "data_points": 提取的具体数据 [{"metric": "指标", "value": "数值", "period": "时间范围", "source": "来源名"}]
   - "source_refs": 支撑该发现的来源 ID 列表

2. "synthesis": 完整的 Markdown 综合报告（按研究问题分章节，重点分析产品策略、用户体验和竞品对比）

3. "information_gaps": 信息缺口列表

输出纯 JSON，不要 markdown 代码块包裹。""",
)


# ── Profile 注册表 ──────────────────────────────────────────

PROFILES: dict[str, ResearchProfile] = {
    "industry_research": INDUSTRY_RESEARCH,
    "ad_campaign": AD_CAMPAIGN_RESEARCH,
    "product_research": PRODUCT_RESEARCH,
}

DEFAULT_PROFILE = "industry_research"


def get_profile(research_type: str | None) -> ResearchProfile:
    """获取研究类型 Profile，不存在则返回默认"""
    return PROFILES.get(research_type or DEFAULT_PROFILE, INDUSTRY_RESEARCH)
