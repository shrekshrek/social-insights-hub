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
