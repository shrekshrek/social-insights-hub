"""LangGraph 状态图定义

Phase 3 完整图：plan → search → filter → fetch → analyze → evaluate ─┐
                 ↑                                                     │
                 └──────────── (gaps + round < max) ───────────────────┘
                                        │ (sufficient / max reached)
                                        ↓
                                    synthesize → END

必须使用 sync invoke()（Celery gevent worker 约束）。
"""

import logging

from langgraph.graph import StateGraph, END

from src.research_agent.config import MAX_ROUNDS
from src.research_agent.state import ResearchState
from src.research_agent.nodes.planner import plan_node
from src.research_agent.nodes.searcher import search_node
from src.research_agent.nodes.filter import filter_node
from src.research_agent.nodes.fetcher import fetch_node
from src.research_agent.nodes.analyzer import analyze_node
from src.research_agent.nodes.evaluator import evaluate_node
from src.research_agent.nodes.synthesizer import synthesize_node

logger = logging.getLogger(__name__)


def _should_continue(state: ResearchState) -> str:
    """评估后的条件路由：继续搜索或进入综合分析"""
    evaluation = state.get("evaluation")
    if evaluation and evaluation.get("should_continue"):
        return "plan"
    return "synthesize"


def build_research_graph() -> StateGraph:
    """构建完整研究图（含 evaluate 循环）"""
    graph = StateGraph(ResearchState)

    graph.add_node("plan", plan_node)
    graph.add_node("search", search_node)
    graph.add_node("filter", filter_node)
    graph.add_node("fetch", fetch_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "filter")
    graph.add_edge("filter", "fetch")
    graph.add_edge("fetch", "analyze")
    graph.add_edge("analyze", "evaluate")

    # 条件路由：evaluate → plan（继续）或 synthesize（终止）
    graph.add_conditional_edges(
        "evaluate",
        _should_continue,
        {"plan": "plan", "synthesize": "synthesize"},
    )

    graph.add_edge("synthesize", END)

    return graph.compile()


# 编译后的图实例（模块级单例）
research_graph = build_research_graph()


def run_research(
    query: str,
    research_questions: list[str] | None = None,
    research_type: str | None = None,
) -> dict:
    """同步执行研究图

    Parameters
    ----------
    query : 研究主题
    research_questions : 研究问题列表（可选）
    research_type : 研究类型（可选），决定搜索域名和分析视角
                    "industry_research"（默认）| "ad_campaign" | "product_research"

    Returns
    -------
    dict : 最终 state（包含 synthesis, findings, selected 等）
    """
    from src.research_agent.profiles import DEFAULT_PROFILE

    initial_state = {
        "query": query,
        "research_questions": research_questions or [],
        "research_type": research_type or DEFAULT_PROFILE,
        "round": 0,
        "max_rounds": MAX_ROUNDS,
    }

    logger.info("开始研究: query=%s, questions=%d", query, len(initial_state["research_questions"]))

    result = research_graph.invoke(initial_state)

    logger.info(
        "研究完成: query=%s, rounds=%d, sources=%d, synthesis_len=%d",
        query,
        result.get("round", 1),
        len(result.get("selected", [])),
        len(result.get("synthesis", "")),
    )
    return result
