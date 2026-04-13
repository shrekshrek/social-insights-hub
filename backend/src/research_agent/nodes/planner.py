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
3. 生成 3-5 个精准搜索关键词（中文为主，必要时加英文）
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


def plan_node(state: ResearchState) -> dict:
    """生成或调整搜索计划

    第 1 轮：基于 query + research_questions 生成初始计划
    后续轮次：基于 evaluation.gap_questions 生成补充搜索计划
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
        suggested_kw = evaluation.get("suggested_keywords", [])
        suffix_parts = []
        if gap_questions:
            suffix_parts.append(
                "⚠️ 这是补充搜索轮次，以下问题在前一轮数据不足：\n"
                + "\n".join(f"- {q}" for q in gap_questions)
                + "\n请针对这些缺口问题生成新的搜索关键词，避免重复之前的搜索。"
            )
        if suggested_kw:
            suffix_parts.append(f"参考关键词方向：{', '.join(suggested_kw)}")
        if suffix_parts:
            extra_context = (context + "\n\n" + "\n".join(suffix_parts)).strip()

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

    # 第 1 轮：写回生成的标题；研究问题已由用户在 preview 步骤确认，不再覆盖
    if current_round == 0:
        generated_title = plan.get("title", "")
        if generated_title:
            result["title"] = generated_title
            logger.info("plan 节点生成标题: %s", generated_title)

    return result
