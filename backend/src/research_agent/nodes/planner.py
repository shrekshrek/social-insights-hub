"""Plan 节点：LLM 梳理用户输入，生成结构化搜索计划

用户输入可能是随意的自然语言，需要 LLM 理解研究范围、
提取核心主题，生成关键词 + 目标源 + 搜索角度。
根据 research_type 使用不同 Profile 的 planner_context。
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
2. 生成 3-5 个精准搜索关键词（中文为主，必要时加英文）
3. 推荐 5-10 个目标搜索域名——必须是与该研究领域相关的权威网站
4. 列出 2-4 个搜索角度

输出 JSON 格式：
{{
    "keywords": ["关键词1", "关键词2", ...],
    "target_domains": ["domain1.com", "domain2.com", ...],
    "search_angles": ["角度1", "角度2", ...]
}}

target_domains 要求：
- 必须是发布专业内容的权威网站
- 根据研究主题选择该领域最权威的来源

{planner_context}

只输出 JSON，不要其他内容。"""


def plan_node(state: ResearchState) -> dict:
    """生成或调整搜索计划

    第 1 轮：基于 query + research_questions 生成初始计划
    后续轮次：基于 evaluation.gap_questions 生成补充搜索计划
    """
    query = state["query"]
    questions = state.get("research_questions", [])
    evaluation = state.get("evaluation")
    current_round = state.get("round", 0)
    profile = get_profile(state.get("research_type"))

    system_prompt = PLAN_SYSTEM_TEMPLATE.format(
        planner_context=profile.planner_context,
    )

    user_content = f"研究主题：{query}"
    if questions:
        user_content += "\n研究问题：\n" + "\n".join(
            f"- {q}" for q in questions
        )

    # 后续轮次：聚焦未覆盖的问题
    if current_round > 0 and evaluation:
        gap_questions = evaluation.get("gap_questions", [])
        suggested_kw = evaluation.get("suggested_keywords", [])
        if gap_questions:
            user_content += "\n\n⚠️ 这是补充搜索轮次，以下问题在前一轮数据不足：\n"
            user_content += "\n".join(f"- {q}" for q in gap_questions)
            user_content += "\n请针对这些缺口问题生成新的搜索关键词，避免重复之前的搜索。"
        if suggested_kw:
            user_content += f"\n参考关键词方向：{', '.join(suggested_kw)}"

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
        plan = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.warning("plan 节点 LLM 输出解析失败，使用回退方案: %s", response.content[:200])
        plan = {
            "keywords": [query],
            "target_domains": [],
            "search_angles": [],
        }

    return {
        "search_plan": {
            "keywords": plan.get("keywords", [query]),
            "target_domains": plan.get("target_domains", []),
            "search_angles": plan.get("search_angles", []),
        },
        "round": state.get("round", 0) + 1,
    }
