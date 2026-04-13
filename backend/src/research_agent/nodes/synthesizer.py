"""Synthesize 节点：输出结构化研究结果

产出 findings_by_question（按研究问题组织的发现，含 confidence/data_points）
+ synthesis（markdown 综合报告）+ coverage 元信息 + information_gaps。
Phase 1 基于 snippets，Phase 2 基于全文 findings。
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def synthesize_node(state: ResearchState) -> dict:
    """综合分析所有搜索结果，输出结构化研究结果"""
    selected = state.get("selected", [])
    query = state["query"]
    questions = state.get("research_questions", [])
    profile = get_profile()

    if not selected:
        empty_findings = {
            q: {
                "answer_summary": "未找到相关数据",
                "confidence": "low",
                "data_points": [],
                "source_refs": [],
            }
            for q in questions
        }
        return {
            "findings_by_question": empty_findings,
            "synthesis": f"# {query}\n\n未找到相关研究报告和文献，建议调整搜索关键词后重试。",
            "coverage": _build_coverage(empty_findings, selected),
            "information_gaps": [f"所有研究问题均缺乏数据：{', '.join(questions)}"],
        }

    # 优先使用 findings（Phase 2+ 深度分析产出），回退到 snippets
    findings = state.get("findings", [])

    sources_for_prompt = []
    if findings:
        # Phase 2+：使用结构化 findings
        for i, f in enumerate(findings):
            key_points_text = "\n    ".join(f.get("key_points", [])[:5])
            data_points_text = ""
            for dp in f.get("data_points", [])[:5]:
                data_points_text += f"\n    - {dp.get('metric', '')}: {dp.get('value', '')} ({dp.get('period', '')})"

            rtq_text = ""
            for q, summary in f.get("relevance_to_questions", {}).items():
                if summary and "无直接相关" not in summary and "无相关" not in summary:
                    rtq_text += f"\n    [{q}]: {summary}"

            sources_for_prompt.append(
                f"[src_{i}] {f.get('source_title', '')} ({f.get('source_tier', 'tier3')})\n"
                f"  核心观点:\n    {key_points_text}"
                + (f"\n  数据点:{data_points_text}" if data_points_text else "")
                + (f"\n  问题相关性:{rtq_text}" if rtq_text else "")
            )
    else:
        # Phase 1 回退：使用 snippets
        for i, c in enumerate(selected):
            sources_for_prompt.append(
                f"[src_{i}] {c['title']} ({c.get('source_tier', 'tier3')})\n"
                f"  URL: {c['url']}\n"
                f"  摘要: {c['snippet']}"
            )

    sources_text = "\n\n".join(sources_for_prompt)

    source_desc = f"{len(findings) or len(selected)} 条分析结果"
    user_content = f"研究主题：{query}\n\n"
    user_content += "研究问题：\n" + "\n".join(f"- {q}" for q in questions)
    user_content += f"\n\n来源材料（共 {source_desc}）：\n\n{sources_text}"

    llm = ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_CHAT_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_CHAT_MAX_TOKENS,
        timeout=120.0,
        max_retries=1,
    )
    response = llm.invoke(
        [
            SystemMessage(content=profile.synthesizer_prompt),
            HumanMessage(content=user_content),
        ]
    )

    # 解析 LLM 结构化输出
    result = _parse_synthesis_response(response.content, questions, selected)

    logger.info(
        "synthesize 节点: %d 条来源, %d 个问题, synthesis %d 字",
        len(selected),
        len(questions),
        len(result.get("synthesis", "")),
    )
    return result


def _normalize_gaps(gaps: list) -> list[str]:
    """将 information_gaps 规范化为字符串列表（LLM 有时输出对象）"""
    result = []
    for item in gaps:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # 合并结构化字段为可读字符串
            question = item.get("question", "")
            desc = item.get("gap_description", "")
            direction = item.get("suggested_research_direction", "")
            parts = [p for p in [question, desc, direction] if p]
            result.append("；".join(parts))
        else:
            result.append(str(item))
    return result


def _parse_synthesis_response(
    content: str,
    questions: list[str],
    selected: list[dict],
) -> dict:
    """解析 LLM 的结构化输出，带回退逻辑"""
    try:
        text = content.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        parsed = json.loads(text)

        findings_by_question = parsed.get("findings_by_question", {})
        synthesis = parsed.get("synthesis", "")
        information_gaps = _normalize_gaps(parsed.get("information_gaps", []))

    except (json.JSONDecodeError, IndexError):
        logger.warning("synthesize LLM 输出非 JSON，回退为纯 markdown")
        findings_by_question = {
            q: {
                "answer_summary": "见综合报告",
                "confidence": "medium",
                "data_points": [],
                "source_refs": [f"src_{i}" for i in range(len(selected))],
            }
            for q in questions
        }
        synthesis = content.strip()
        information_gaps = []

    coverage = _build_coverage(findings_by_question, selected)

    return {
        "findings_by_question": findings_by_question,
        "synthesis": synthesis,
        "coverage": coverage,
        "information_gaps": information_gaps,
    }


def _build_coverage(
    findings_by_question: dict,
    selected: list[dict],
) -> dict:
    """构建 coverage 元信息"""
    high_count = 0
    covered_count = 0
    for qf in findings_by_question.values():
        conf = qf.get("confidence", "low") if isinstance(qf, dict) else "low"
        if conf in ("high", "medium"):
            covered_count += 1
        if conf == "high":
            high_count += 1

    tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
    for c in selected:
        tier = c.get("source_tier", "tier3")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return {
        "questions_covered": covered_count,
        "questions_total": len(findings_by_question),
        "high_confidence_count": high_count,
        "source_quality": tier_counts,
    }
