"""Plan 节点：LLM 梳理用户输入，生成结构化搜索计划

用户输入可能是随意的自然语言，需要 LLM 理解研究范围、
提取核心主题，生成关键词 + 目标源 + 搜索角度。
使用行业报告研究 Profile 的 planner_context。
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)

PLAN_SYSTEM_TEMPLATE = """你是一个专业的研究规划师。用户会给你一个研究主题和（可选的）研究问题。

你的任务：
1. 理解研究范围，补全不完整的描述
2. 如果用户未提供研究问题，根据研究主题自动生成 3-5 个具体的研究问题（每个问题应聚焦一个可回答的子维度）
3. 生成 5-8 个搜索关键词，规则：
   - 每个关键词必须包含以下报告类修饰词之一："报告"、"白皮书"、"研究报告"、"PDF"、"report"、"whitepaper"
   - 至少 2 个中文关键词，至少 1 个英文关键词
   - 优先格式：[机构/行业] + [年份] + [修饰词]，例如："2024新能源汽车行业报告 PDF"、"China consumer market report 2024"
   - 涉及买方行为/决策类研究时，额外生成采购视角关键词，例如："企业采购咨询服务决策流程 研究报告"、"B2B buyer behavior consulting report"
4. 推荐 5-10 个目标搜索域名——必须是与该研究领域相关的权威网站
5. 列出 2-4 个搜索角度

输出 JSON 格式：
{{
    "title": "简短研究标题（10字以内）",
    "analysis_goal": "核心研究意图（1-2句话）",
    "research_questions": ["研究问题1", "研究问题2", ...],
    "keywords": ["关键词1", "关键词2", ...],
    "target_domains": ["domain1.com", "domain2.com", ...],
    "search_angles": ["角度1", "角度2", ...]
}}

title 要求：
- 10 个中文字以内的简短概括，作为任务列表中的显示标题
- 提炼研究主题的核心对象和目的，例如"新能源汽车竞争格局"、"EY品牌认知渠道"

analysis_goal 要求：
- 1-2 句话，提炼核心研究意图，明确研究对象、核心问题和预期产出
- 不是 Brief 原文的复制，而是面向研究执行的精炼表述
- 后续所有节点（筛选、分析、综合）都以此为锚点判断内容相关性
- 例如："研究中国B2B企业在选择咨询合作伙伴时的信息获取渠道与决策标准，产出媒体生态与行为洞察"

research_questions 要求：
- 如果用户已提供研究问题：在保留用户原始意图的基础上优化——将模糊问题拆分为具体子问题、补充用户可能遗漏的关键维度、使问题更适合搜索引擎检索。最终输出 3-5 个优化后的问题
- 如果用户未提供：根据主题自动生成 3-5 个，覆盖研究主题的关键子维度
- 每个问题应具体、可回答、可用搜索引擎找到相关资料

target_domains 要求：
- 必须是发布专业内容的权威网站
- 根据研究主题选择该领域最权威的来源

{planner_context}

只输出 JSON，不要其他内容。"""


def call_planner_llm(
    query: str,
    context: str = "",
    research_questions: list[str] | None = None,
) -> dict:
    """调用 planner LLM，返回结构化研究计划（同步，可复用于 preview 接口）

    Returns
    -------
    dict : 包含 title / description / research_questions / keywords / target_domains / search_angles
    """
    profile = get_profile()
    system_prompt = PLAN_SYSTEM_TEMPLATE.format(planner_context=profile.planner_context)

    user_content = f"研究主题：{query}"
    if context:
        user_content += f"\n研究背景：{context}"
    if research_questions:
        user_content += "\n研究问题：\n" + "\n".join(f"- {q}" for q in research_questions)

    llm = ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_CHAT_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_CHAT_MAX_TOKENS,
        timeout=60.0,
        max_retries=1,
    )
    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]
    )

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        return json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.warning("planner LLM 输出解析失败，使用回退方案: %s", response.content[:200])
        return {
            "title": query[:20],
            "analysis_goal": query[:100],
            "keywords": [query],
            "target_domains": [],
            "search_angles": [],
            "research_questions": [],
        }


def _build_tried_domains(findings: list[dict]) -> list[str]:
    """从历史 findings 中提取已尝试过的域名（去重，最多返回15个）"""
    from urllib.parse import urlparse
    seen: dict[str, int] = {}
    for f in findings:
        url = f.get("source_url", "")
        if not url:
            continue
        domain = urlparse(url).netloc.lstrip("www.")
        seen[domain] = seen.get(domain, 0) + 1
    # 按出现次数降序，返回最多15个
    return [d for d, _ in sorted(seen.items(), key=lambda x: -x[1])[:15]]


def plan_node(state: ResearchState) -> dict:
    """生成或调整搜索计划

    第 1 轮：基于 query + research_questions 生成初始计划
    后续轮次：基于 evaluation.gap_questions 生成补充搜索计划，
              并注入已尝试域名和方向诊断，引导 LLM 换角度搜索。
    """
    query = state["query"]
    questions = state.get("research_questions", [])
    evaluation = state.get("evaluation")
    current_round = state.get("round", 0)
    context = state.get("context", "")

    # 后续轮次：追加缺口问题提示后再调 LLM
    extra_context = context
    if current_round > 0 and evaluation:
        gap_questions = evaluation.get("gap_questions", [])
        covered_count = len(evaluation.get("questions_covered", []))
        total_count = len(questions)
        findings = state.get("findings", [])
        tried_domains = _build_tried_domains(findings)

        suffix_parts: list[str] = []

        if gap_questions:
            suffix_parts.append(
                "⚠️ 这是补充搜索轮次，以下问题在前一轮数据不足：\n"
                + "\n".join(f"- {q}" for q in gap_questions)
                + "\n请针对这些缺口问题生成新的搜索关键词，避免重复之前的搜索。"
            )

        if tried_domains:
            suffix_parts.append(
                "已搜索过的域名（请生成新关键词时尽量避开，转向其他来源）：\n"
                + "、".join(tried_domains)
            )

        # 覆盖率偏低时，注入方向诊断
        if total_count > 0 and covered_count < total_count / 2:
            suffix_parts.append(
                '⚠️ 前几轮覆盖率不足（已覆盖研究问题少于一半）。'
                '请结合当前研究主题自行诊断原因，常见情况包括：\n'
                '- 搜索角度单一，需要换维度（如从行业整体→细分领域、从国内→全球、从现状→趋势）\n'
                '- 来源类型集中，需要多元化（如从行业参与者自身发布→独立第三方研究机构、从中文→中英混搜）\n'
                '- 关键词过于宽泛或过于专业，需要调整颗粒度\n'
                '请根据具体研究主题生成差异化的新关键词，避免重复前几轮的搜索方向。'
            )

        if suffix_parts:
            extra_context = (context + "\n\n" + "\n\n".join(suffix_parts)).strip()

    plan = call_planner_llm(
        query=query,
        context=extra_context,
        research_questions=questions or None,
    )

    result: dict = {
        "search_plan": {
            "keywords": plan.get("keywords", [query]),
            "target_domains": plan.get("target_domains", []),
            "search_angles": plan.get("search_angles", []),
        },
        "round": state.get("round", 0) + 1,
    }

    # 第 1 轮：写回生成的标题和研究问题（仅在状态中没有对应字段时补全）
    if current_round == 0:
        if not state.get("title"):
            generated_title = plan.get("title", "")
            if generated_title:
                result["title"] = generated_title
                logger.info("plan 节点生成标题: %s", generated_title)
        if not questions:
            generated_questions = plan.get("research_questions", [])
            if generated_questions:
                result["research_questions"] = generated_questions
                logger.info("plan 节点生成研究问题: %d 个", len(generated_questions))

    return result
