"""Search 节点：执行 Tavily 搜索，候选不足时降级到 Crawl4AI

执行流程：
1. 使用 Tavily 对每个关键词做定向域名搜索
2. 若候选总量低于阈值，追加 Crawl4AI 全网搜索（Baidu/Bing）作为补充
"""

import logging

from src.config import get_settings
from src.research_agent.config import MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK
from src.research_agent.state import ResearchState
from src.research_agent.tools.web_search import tavily_search

logger = logging.getLogger(__name__)


def search_node(state: ResearchState) -> dict:
    """执行搜索，收集候选结果"""
    plan = state["search_plan"]
    keywords = plan.get("keywords", [])
    target_domains = plan.get("target_domains", [])

    settings = get_settings()

    # 域名合并：config 全局默认 + LLM 针对本次主题推荐
    all_domains = list(set(settings.RESEARCH_AGENT_TARGET_DOMAINS + target_domains))

    # 为不含报告类修饰词的关键词追加"报告"变体，提升报告类内容命中率
    report_indicators = {"报告", "白皮书", "研究报告", "PDF", "report", "whitepaper"}
    effective_keywords: list[str] = []
    for kw in keywords:
        effective_keywords.append(kw)
        if not any(ind.lower() in kw.lower() for ind in report_indicators):
            effective_keywords.append(f"{kw} 报告")

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
        "search 节点 [Tavily]: %d 个关键词 → %d 条候选",
        len(keywords),
        len(all_candidates),
    )

    # Tavily 候选不足时，降级到 Crawl4AI 全网搜索补充
    if len(all_candidates) < MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK:
        logger.info(
            "候选数 %d < %d，启动 Crawl4AI 补充搜索",
            len(all_candidates),
            MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK,
        )
        from src.research_agent.tools.crawl4ai_search import crawl4ai_search

        # 对前 3 个关键词补充（避免过多请求）
        for kw in effective_keywords[:3]:
            extra = crawl4ai_search(kw, max_results=15)
            for r in extra:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_candidates.append(r)

        logger.info(
            "search 节点 [Crawl4AI 补充]: 总计 %d 条候选",
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
