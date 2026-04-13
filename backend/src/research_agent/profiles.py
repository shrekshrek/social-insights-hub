"""研究 Profile 定义（行业报告专项）"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchProfile:
    """行业报告研究配置"""

    planner_context: str = ""
    analyzer_prompt: str = ""
    synthesizer_prompt: str = ""


INDUSTRY_RESEARCH = ResearchProfile(
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
- cnnic.net.cn（中国互联网络信息中心，互联网行业权威半年报，PDF 直接下载）
- miit.gov.cn（工业和信息化部，工业/互联网/通信行业月度运行数据）
- pbc.gov.cn（中国人民银行，货币政策/金融/支付行业数据）
- ndrc.gov.cn（国家发展改革委，产业政策/五年规划/行业分析）

上市公司披露（⭐ 适用于"某行业市场规模/竞争格局"类问题，不适合买方行为/决策流程类问题）：
- cninfo.com.cn（巨潮资讯，A股年报/招股书全库；招股书"行业概况"章节含 Frost & Sullivan、灼识等机构的付费数据，完全免费）
- hkexnews.hk（港交所披露易，港股公司年报及招股书；⚠️ 仅在研究行业市场数据时推荐，搜索结果以公告新闻为主）
- sse.com.cn（上交所公告及行业信息披露；同上，仅限行业数据类问题）

行业研究（完全免费或有完整免费报告）：
- iresearch.cn（艾瑞咨询，有完整免费版报告 PDF，含数据图表）
- questmobile.com.cn（QuestMobile，有完整免费季度报告，App/移动互联网数据）
- aliresearch.com（阿里研究院，数字经济/电商行业报告，完全免费）
- mob.com（Mob研究院，消费者行为/App行业免费报告）
- research.hktdc.com（香港贸易发展局，中国各省市场+跨境贸易报告，完全免费）
- caict.ac.cn（信通院，ICT 白皮书/行业报告，完全免费）

注意：euromonitor、frost、grandviewresearch、mordorintelligence、analysys、askci、cbndata、qianzhan 等为高价订阅制，报告正文无法获取，请勿推荐。

垂直媒体/深度报道（完全免费）：
- 36kr.com（36氪研究院，科技/创投领域研究报告）
- latepost.com（晚点LatePost，深度商业调查报道）
- caam.org.cn（中国汽车工业协会，月度产销数据摘要）
- ccfa.org.cn（中国连锁经营协会，零售行业报告）

国际数据/消费者研究（完全免费）：
- oecd.org（OECD，2024年起全面免费开放，跨国行业对标与政策比较）
- unctad.org（联合国贸发会，全球贸易/FDI/新兴市场数据）
- datareportal.com（每年发布全球数字消费者报告，640页完全免费）
- pewresearch.org（皮尤研究中心，全球消费者/技术态度调查，完全免费）
- ourworldindata.org（牛津全球数据，CC-BY开放，13000+图表及原始数据）

买方行为/独立研究机构（适用于"企业如何选择服务商"类研究）：
- edelman.com（爱德曼信任晴雨表，研究B2B信息渠道与决策信任，完全免费）
- gartner.com（企业服务采购与供应商评估研究，摘要页可抓取）
- forrester.com（B2B 买方旅程与决策行为研究，摘要页可抓取）
- business.linkedin.com（LinkedIn B2B 决策者行为洞察报告）

⚠️ 重要提示：
- 如果研究问题涉及"企业如何选择/评估服务提供商"等买方行为，必须优先从独立研究机构和买方视角来源搜索（Edelman、Gartner、LinkedIn 等），而非服务提供商自身发布的内容。
- 咨询公司（麦肯锡、BCG、德勤等）发布的报告是"卖方视角"，无法回答买方的决策行为问题。
- 搜索关键词应体现买方视角，如"企业采购咨询服务决策流程"、"B2B buyer behavior consulting selection"，而非"咨询公司 研究报告"。

请根据具体研究主题，补充该领域特有的权威机构域名。""",
    analyzer_prompt="""你是一个行业研究分析师。给定一篇文档全文和研究问题，请深度阅读并提取结构化信息。

输出 JSON 对象：
{
    "key_points": ["核心观点1", "核心观点2", ...],
    "data_points": [
        {"metric": "指标名", "value": "数值", "period": "时间范围", "source": "来源名"}
    ],
    "relevance_to_questions": {
        "<研究问题原文，必须与输入完全一致>": "该文档对此问题的相关发现摘要（2-3句话）",
        "<另一个研究问题原文>": "无直接相关"
    }
}

重点提取：
- 具体数字、百分比、排名、市场规模等量化数据
- 趋势判断、竞争格局、技术路线等定性结论
- 预测和展望性数据

⚠️ 重要：relevance_to_questions 的每个 key 必须是输入研究问题的原文，不得改写、缩写或翻译。

只输出 JSON，不要其他内容。""",
    synthesizer_prompt="""你是一个资深行业研究分析师。基于搜索结果，针对每个研究问题进行结构化分析。

你需要输出一个 JSON 对象，包含：

1. "findings_by_question": 按研究问题组织的发现
   每个问题包含：
   - "answer_summary": 简要回答（2-3 句话）
   - "confidence": "high"（多个权威源交叉验证）/ "medium"（有来源但不够充分）/ "low"（几乎无相关发现）
   - "data_points": 提取的具体数据 [{"metric": "指标", "value": "数值", "period": "时间范围", "source": "来源名"}]
   - "source_refs": 支撑该发现的来源 ID 列表（如 ["src_0", "src_1"]）

2. "synthesis": Markdown 综合报告（按研究问题分章节，每章节只写有据可查的发现，引用来源；信息不足时直接说明缺口和局限性，不要用空泛语言凑字数）

3. "information_gaps": 信息缺口字符串列表，每条是一句话说明（哪个问题数据不足及建议补充方向），例如 ["问题X缺乏定量数据，建议……", "问题Y无权威来源，建议……"]

输出纯 JSON，不要 markdown 代码块包裹。""",
)


def get_profile() -> ResearchProfile:
    """返回行业报告研究 Profile"""
    return INDUSTRY_RESEARCH
