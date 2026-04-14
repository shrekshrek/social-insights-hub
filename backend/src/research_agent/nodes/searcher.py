"""Search 节点：执行搜索，候选不足时降级到 Crawl4AI

支持两个 search provider（由 SEARCH_PROVIDER 环境变量控制）：
- tavily（默认）：snippet 模式，fetcher 节点负责抓取全文
- exa：直接返回全文（20k chars），可跳过 fetcher 节点抓取

执行流程：
1. 按 provider 对每个关键词做定向域名搜索
2. 若候选总量低于阈值，追加 Crawl4AI 全网搜索（Baidu/Bing）作为补充
"""

import logging
from urllib.parse import urlparse

from src.config import get_settings
from src.research_agent.config import MIN_CANDIDATES_BEFORE_CRAWL4AI_FALLBACK
from src.research_agent.nodes.filter import _extract_year
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)

# 单域名进入候选池的最大条数（filter 层上限为 3，此处取 1.67 倍给 filter 留选择空间）
_MAX_CANDIDATES_PER_DOMAIN = 5


def _saturated_domains(findings: list[dict], min_count: int = 2) -> set[str]:
    """从已分析 findings 中找出已充分采集的域名（出现 min_count 次及以上）"""
    domain_count: dict[str, int] = {}
    for f in findings:
        url = f.get("source_url", "")
        if not url:
            continue
        domain = urlparse(url).netloc.lower().lstrip("www.")
        domain_count[domain] = domain_count.get(domain, 0) + 1
    return {d for d, cnt in domain_count.items() if cnt >= min_count}


def search_node(state: ResearchState) -> dict:
    """执行搜索，收集候选结果"""
    plan = state["search_plan"]
    keywords = plan.get("keywords", [])
    target_domains = plan.get("target_domains", [])
    current_round = state.get("round", 1)

    settings = get_settings()

    # 域名合并：config 全局默认 + LLM 针对本次主题推荐
    all_domains = list(set(settings.RESEARCH_AGENT_TARGET_DOMAINS + target_domains))

    # 第 3 轮起：从 target_domains 移除已充分采集的域名（≥2 篇已分析），
    # 强制 Tavily 在尚未充分搜索的来源中寻找内容，避免强势域名持续垄断
    if current_round >= 3:
        findings = state.get("findings", [])
        saturated = _saturated_domains(findings, min_count=2)
        if saturated:
            reduced = [
                d for d in all_domains
                if not any(
                    d == s or d.endswith("." + s) or s.endswith("." + d)
                    for s in saturated
                )
            ]
            # 保底：至少保留 10 个域名，避免过度限制
            if len(reduced) >= 10:
                logger.info(
                    "search 节点 round=%d: 移除已饱和域名 %d 个，剩余 %d 个",
                    current_round, len(saturated), len(reduced),
                )
                all_domains = reduced

    # planner 已强制每个关键词含报告类修饰词，无需再追加变体
    provider = settings.SEARCH_PROVIDER.lower()
    all_candidates, seen_urls = _run_search(provider, keywords, all_domains)

    # 候选池域名限流：单域名最多 _MAX_CANDIDATES_PER_DOMAIN 条
    # 防止 assets.kpmg.com 等高产域名霸占候选池，挤占其他来源的曝光机会
    before_cap = len(all_candidates)
    all_candidates = _cap_candidates_by_domain(all_candidates, _MAX_CANDIDATES_PER_DOMAIN)
    if len(all_candidates) < before_cap:
        logger.info(
            "search 节点: 候选池域名限流 %d → %d 条",
            before_cap,
            len(all_candidates),
        )

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

        for kw in keywords[:3]:
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
                snippet = r["snippet"]
                # snippet 通常含发布年份，作为 URL/标题都无年份时的兜底
                year = _extract_year(url) or _extract_year(title) or _extract_year(snippet)
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


def _cap_candidates_by_domain(candidates: list[dict], max_per_domain: int) -> list[dict]:
    """对候选池按域名限流，保留每个域名最靠前的 max_per_domain 条"""
    domain_count: dict[str, int] = {}
    result = []
    for c in candidates:
        domain = urlparse(c.get("url", "")).netloc.lstrip("www.")
        if domain_count.get(domain, 0) < max_per_domain:
            result.append(c)
            domain_count[domain] = domain_count.get(domain, 0) + 1
    return result


def _extract_domain(url: str) -> str:
    """从 URL 提取域名"""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def _guess_content_type(url: str) -> str:
    """根据 URL 猜测内容类型"""
    lower = url.lower()
    if lower.endswith(".pdf") or "/pdf/" in lower:
        return "pdf"
    return "html"
