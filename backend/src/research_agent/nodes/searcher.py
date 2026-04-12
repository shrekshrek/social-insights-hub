"""Search 节点：执行 Tavily 搜索

对 search_plan 中的每个关键词执行搜索，合并去重。
"""

import logging

from src.config import get_settings
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState
from src.research_agent.tools.web_search import tavily_search

logger = logging.getLogger(__name__)


def search_node(state: ResearchState) -> dict:
    """执行搜索，收集候选结果"""
    plan = state["search_plan"]
    keywords = plan.get("keywords", [])
    target_domains = plan.get("target_domains", [])

    settings = get_settings()
    profile = get_profile(state.get("research_type"))

    # 三层域名合并：config 默认 + profile 专属 + LLM 推荐
    all_domains = list(set(
        settings.RESEARCH_AGENT_TARGET_DOMAINS
        + profile.target_domains
        + target_domains
    ))

    # report 策略：为不含报告类词的关键词追加修饰
    effective_keywords = keywords
    if profile.content_strategy == "report":
        report_indicators = {"报告", "白皮书", "研究报告", "PDF", "report", "whitepaper"}
        augmented = []
        for kw in keywords:
            augmented.append(kw)
            # 如果关键词中不含任何报告类修饰词，追加一条带"报告"的变体
            if not any(ind.lower() in kw.lower() for ind in report_indicators):
                augmented.append(f"{kw} 报告")
        effective_keywords = augmented

    # Tavily 搜索：每个关键词搜索
    all_candidates = []
    seen_urls: set[str] = set()

    for kw in effective_keywords:
        results = tavily_search(
            query=kw,
            target_domains=all_domains,
            max_results=10,
        )
        for r in results:
            url = r["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_candidates.append({
                    "title": r["title"],
                    "url": url,
                    "snippet": r["snippet"],
                    "source": _extract_domain(url),
                    "content_type": _guess_content_type(url),
                    "source_tier": "",  # filter 节点标注
                    "relevance_score": r.get("score", 0.0),
                })

    logger.info(
        "search 节点: %d 个关键词 → %d 条候选（去重后）",
        len(keywords),
        len(all_candidates),
    )

    return {
        "candidates": all_candidates,
    }


def _extract_domain(url: str) -> str:
    """从 URL 提取域名"""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return ""


def _guess_content_type(url: str) -> str:
    """根据 URL 猜测内容类型"""
    lower = url.lower()
    if lower.endswith(".pdf") or "/pdf/" in lower:
        return "pdf"
    return "html"
