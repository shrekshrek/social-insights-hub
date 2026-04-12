"""Filter 节点：LLM 批量评估候选相关性，选出 top N，标注 source_tier

单次 LLM 调用评估所有候选，不逐条评分。
source_tier 分层：tier1=四大/权威智库, tier2=行业机构, tier3=其他。
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.config import MAX_CANDIDATES_PER_ROUND
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)

# 域名 → tier 映射（filter 节点自动标注，LLM 可覆盖）
TIER1_DOMAINS = {
    "mckinsey.com", "mckinsey.com.cn",
    "deloitte.com",
    "pwccn.com", "pwc.com",
    "ey.com",
    "kpmg.com",
    "cssn.cn",
    "drc.gov.cn",
    "stats.gov.cn",
}

TIER2_DOMAINS = {
    "iresearch.cn", "analysys.cn",
    "questmobile.com.cn",
    "caict.ac.cn",
    "worldbank.org",
    "imf.org",
}

FILTER_SYSTEM_PROMPT = """你是一个研究文献筛选专家。给定一组搜索结果和研究问题，请评估每条结果的相关性。

对每条结果打分（0-1），选出最相关的 {max_n} 条。

{strategy_hint}

输出 JSON 数组，每个元素包含：
- "index": 原始列表中的序号（从 0 开始）
- "score": 相关性评分（0-1）
- "reason": 一句话理由

只输出 JSON 数组，按 score 降序排列，不要其他内容。"""

REPORT_FILTER_HINT = """评分加权规则：
- URL 以 .pdf 结尾或标题含"报告""白皮书""研究""report"等词的结果，相关性加 0.15 分
- 来源为权威咨询/研究机构的结果优先选择
- 普通资讯网页（非报告类）相关性应降低"""


def _classify_source_tier(domain: str) -> str:
    """根据域名分类来源层级"""
    domain_lower = domain.lower().lstrip("www.")
    for t1 in TIER1_DOMAINS:
        if t1 in domain_lower:
            return "tier1"
    for t2 in TIER2_DOMAINS:
        if t2 in domain_lower:
            return "tier2"
    return "tier3"


def filter_node(state: ResearchState) -> dict:
    """筛选候选结果并标注 source_tier"""
    candidates = state.get("candidates", [])
    questions = state.get("research_questions", [])
    query = state["query"]

    if not candidates:
        return {"selected": []}

    # 先标注 source_tier（基于域名规则）
    for c in candidates:
        c["source_tier"] = _classify_source_tier(c.get("source", ""))

    # report 策略：候选少时也走 LLM 筛选以偏好 PDF 内容
    profile = get_profile(state.get("research_type"))
    is_report_strategy = profile.content_strategy == "report"

    # 少于阈值直接全选（report 策略除外 — 需要 LLM 偏好 PDF）
    if len(candidates) <= MAX_CANDIDATES_PER_ROUND and not is_report_strategy:
        return {"selected": candidates}

    # report 策略：将 PDF 候选排在前面（LLM 兜底前的硬排序）
    if is_report_strategy:
        candidates = sorted(
            candidates,
            key=lambda c: (0 if c.get("content_type") == "pdf" else 1),
        )

    # 构造候选列表文本
    candidates_text = "\n".join(
        f"[{i}] {c['title']}\n    URL: {c['url']}\n    类型: {c.get('content_type', 'html')}\n    摘要: {c['snippet'][:200]}"
        for i, c in enumerate(candidates)
    )

    user_content = f"研究主题：{query}\n"
    if questions:
        user_content += "研究问题：\n" + "\n".join(f"- {q}" for q in questions)
    user_content += f"\n\n候选结果（共 {len(candidates)} 条）：\n{candidates_text}"

    strategy_hint = REPORT_FILTER_HINT if is_report_strategy else ""

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
            SystemMessage(
                content=FILTER_SYSTEM_PROMPT.format(
                    max_n=MAX_CANDIDATES_PER_ROUND,
                    strategy_hint=strategy_hint,
                )
            ),
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
        scored = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.warning(
            "filter 节点解析失败，取前 %d 条: %s",
            MAX_CANDIDATES_PER_ROUND,
            response.content[:200],
        )
        return {"selected": candidates[:MAX_CANDIDATES_PER_ROUND]}

    # 按 LLM 打分选出 top N
    selected = []
    for item in scored[:MAX_CANDIDATES_PER_ROUND]:
        idx = item.get("index", -1)
        if 0 <= idx < len(candidates):
            selected.append({
                **candidates[idx],
                "relevance_score": item.get("score", 0.0),
            })

    if not selected:
        selected = candidates[:MAX_CANDIDATES_PER_ROUND]

    logger.info("filter 节点: %d → %d 条", len(candidates), len(selected))
    return {"selected": selected}
