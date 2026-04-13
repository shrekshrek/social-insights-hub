"""Search 节点：执行搜索，候选不足时降级到 Crawl4AI

支持两个 search provider（由 SEARCH_PROVIDER 环境变量控制）：
- tavily（默认）：snippet 模式，fetcher 节点负责抓取全文
- exa：直接返回全文（20k chars），可跳过 fetcher 节点抓取

执行流程：
1. 按 provider 对每个关键词做定向域名搜索
2. 若候选总量低于阈值，追加 Crawl4AI 全网搜索（Baidu/Bing）作为补充
"""

import logging

from src.config import get_settings
from src.research_agent.config import MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK
from src.research_agent.nodes.filter import _extract_year
from src.research_agent.state import ResearchState

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

    provider = settings.SEARCH_PROVIDER.lower()
    all_candidates, seen_urls = _run_search(provider, effective_keywords, all_domains)

    logger.info(
        "search 节点 [%s]: %d 个关键词 → %d 条候选",
        provider,
        len(keywords),
        len(all_candidates),
    )

    # 候选不足时，降级到 Crawl4AI 全网搜索补充
    if len(all_candidates) < MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK:
        logger.info(
            "候选数 %d < %d，启动 Crawl4AI 补充搜索",
            len(all_candidates),
            MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK,
        )
        from src.research_agent.tools.crawl4ai_search import crawl4ai_search

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

    return {"candidates": all_candidates}


def _run_search(
    provider: str,
    keywords: list[str],
    target_domains: list[str],
) -> tuple[list[dict], set[str]]:
    """按 provider 执行搜索，返回 (candidates, seen_urls)"""
    if provider == "exa":
        return _search_exa(keywords, target_domains)
    return _search_tavily(keywords, target_domains)


def _search_tavily(
    keywords: list[str],
    target_domains: list[str],
) -> tuple[list[dict], set[str]]:
    from src.research_agent.tools.web_search import tavily_search

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        for r in tavily_search(query=kw, target_domains=target_domains, max_results=10):
            url = r["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                title = r["title"]
                year = _extract_year(url) or _extract_year(title)
                candidates.append({
                    "title": title,
                    "url": url,
                    "snippet": r["snippet"],
                    "full_text": "",  # fetcher 节点负责填充
                    "source": _extract_domain(url),
                    "content_type": _guess_content_type(url),
                    "source_tier": "",
                    "relevance_score": r.get("score", 0.0),
                    "published_date": str(year) if year else "",
                })

    return candidates, seen_urls


def _search_exa(
    keywords: list[str],
    target_domains: list[str],
) -> tuple[list[dict], set[str]]:
    from src.research_agent.tools.exa_search import exa_search

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        for r in exa_search(query=kw, target_domains=target_domains, max_results=10):
            url = r["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                title = r["title"]
                pub_date = r.get("published_date", "")
                # Exa 日期格式为 ISO（2024-05-01），截取年份作为回退
                if not pub_date:
                    year = _extract_year(url) or _extract_year(title)
                    pub_date = str(year) if year else ""
                candidates.append({
                    "title": title,
                    "url": url,
                    "snippet": r["snippet"],
                    "full_text": r.get("full_text", ""),  # Exa 直接返回全文
                    "source": _extract_domain(url),
                    "content_type": _guess_content_type(url),
                    "source_tier": "",
                    "relevance_score": r.get("score", 0.0),
                    "published_date": pub_date,
                })

    return candidates, seen_urls


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
