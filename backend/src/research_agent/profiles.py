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


def get_profile() -> ResearchProfile:
    """返回行业报告研究 Profile"""
    return INDUSTRY_RESEARCH
