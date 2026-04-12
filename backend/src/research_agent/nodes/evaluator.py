"""Evaluate 节点：评估研究覆盖度，决定是否继续搜索

检查逻辑：
1. 每个研究问题是否有 findings 覆盖？confidence 如何？
2. tier1 来源数量是否足够（>=1）？
3. 是否还有明显信息缺口？
4. 当前轮次是否已达上限？

决策：gap_questions 非空 且 round < max_rounds → should_continue=True
"""

import logging

from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def evaluate_node(state: ResearchState) -> dict:
    """评估覆盖度，输出 Evaluation"""
    findings = state.get("findings", [])
    questions = state.get("research_questions", [])
    selected = state.get("selected", [])
    current_round = state.get("round", 1)
    max_rounds = state.get("max_rounds", 3)

    # 统计每个问题的覆盖情况
    question_coverage: dict[str, list[str]] = {q: [] for q in questions}
    for finding in findings:
        rtq = finding.get("relevance_to_questions", {})
        for q in questions:
            relevance = rtq.get(q, "")
            if relevance and "无直接相关" not in relevance and "无相关" not in relevance:
                question_coverage[q].append(finding.get("source_title", ""))

    # 判断哪些问题覆盖不足
    covered_questions = []
    gap_questions = []
    for q, sources in question_coverage.items():
        if len(sources) >= 2:
            covered_questions.append(q)
        else:
            gap_questions.append(q)

    # 统计 tier1 来源
    tier1_count = sum(
        1 for c in selected if c.get("source_tier") == "tier1"
    )

    # 生成补充关键词
    suggested_keywords = []
    for gap_q in gap_questions[:3]:
        # 提取问题中的关键信息作为补充搜索词
        suggested_keywords.append(gap_q)

    # 决策：是否继续
    should_continue = (
        len(gap_questions) > 0
        and current_round < max_rounds
    )

    logger.info(
        "evaluate 节点: round=%d/%d, covered=%d/%d, tier1=%d, gaps=%d, continue=%s",
        current_round,
        max_rounds,
        len(covered_questions),
        len(questions),
        tier1_count,
        len(gap_questions),
        should_continue,
    )

    return {
        "evaluation": {
            "questions_covered": covered_questions,
            "gap_questions": gap_questions,
            "tier1_source_count": tier1_count,
            "suggested_keywords": suggested_keywords,
            "should_continue": should_continue,
        },
    }
