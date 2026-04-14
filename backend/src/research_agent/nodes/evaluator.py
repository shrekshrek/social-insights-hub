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

# 回避性表述：包含这些词的 relevance 文本不计入有效覆盖
_HEDGING_PHRASES = [
    "缺乏", "没有直接", "未直接", "未提供", "没有提供",
    "没有专项", "不足", "没有针对", "无专项", "缺少",
    "没有相关", "未涉及", "不涉及",
]
# relevance 文本最低有效长度（过短说明 LLM 只给了泛泛一句话）
_MIN_SUBSTANTIVE_LEN = 60


def _is_substantive(relevance: str) -> bool:
    """判断 relevance 文本是否为实质性答案（非搪塞/回避）"""
    if len(relevance) < _MIN_SUBSTANTIVE_LEN:
        return False
    return not any(phrase in relevance for phrase in _HEDGING_PHRASES)


def evaluate_node(state: ResearchState) -> dict:
    """评估覆盖度，输出 Evaluation"""
    findings = state.get("findings", [])
    questions = state.get("research_questions", [])
    selected = state.get("selected", [])
    current_round = state.get("round", 1)
    max_rounds = state.get("max_rounds", 3)

    # 统计每个问题的实质性覆盖情况
    question_coverage: dict[str, list[str]] = {q: [] for q in questions}
    for finding in findings:
        rtq = finding.get("relevance_to_questions", {})
        scores = finding.get("question_relevance_scores", {})
        for q in questions:
            # 优先精确匹配，回退到 key 包含问题片段的模糊匹配（应对 LLM 改写 key）
            relevance = rtq.get(q, "")
            score = scores.get(q)
            if not relevance:
                q_lower = q.lower()
                for rtq_key, rtq_val in rtq.items():
                    if rtq_key and (q_lower in rtq_key.lower() or rtq_key.lower() in q_lower):
                        relevance = rtq_val
                        # 同步查找对应 key 的分数
                        if score is None:
                            score = scores.get(rtq_key)
                        break
            # 无分数时（旧数据/snippet fallback）：仅靠文本判断，不设分数门槛
            # 有分数时：要求 >= 0.5，防止 LLM 为不相关文档写出看似相关的文本
            score_ok = (score is None) or (score >= 0.5)
            # 只计入实质性答案，过滤搪塞/回避性表述
            if (
                relevance
                and "无直接相关" not in relevance
                and "无相关" not in relevance
                and _is_substantive(relevance)
                and score_ok
            ):
                question_coverage[q].append(finding.get("source_title", ""))

    # 需要 >= 2 条实质性来源才视为覆盖（单条来源不足以排除偶然，且无法互相印证）
    # 不对 round 1 放宽：若 round 1 只找到 1 条就停止，质量往往不够，应继续搜索
    min_sources = 2
    covered_questions = []
    gap_questions = []
    for q, sources in question_coverage.items():
        if len(sources) >= min_sources:
            covered_questions.append(q)
        else:
            gap_questions.append(q)

    # 统计 tier1 来源
    tier1_count = sum(
        1 for c in selected if c.get("source_tier") == "tier1"
    )

    # 决策：是否继续
    # selected 为空说明本轮没有新内容，继续也没有意义
    should_continue = (
        len(gap_questions) > 0
        and current_round < max_rounds
        and len(selected) > 0
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
            "should_continue": should_continue,
        },
    }
