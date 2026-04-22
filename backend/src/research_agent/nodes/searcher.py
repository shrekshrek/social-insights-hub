"""Search 节点：Tavily 定向域名搜索

执行流程：
1. 合并 profile 的兜底域名 + planner LLM 针对本次主题推荐的域名
2. 第 3 轮起剔除已充分采集（≥2 篇）的饱和域名，避免强势域名垄断
3. 对每个关键词调 Tavily include_domains 定向搜索
4. 候选池按域名限流（_MAX_CANDIDATES_PER_DOMAIN），防止单域霸占

设计约定（2026-04）：
- **搜索只走 Tavily**——不再做 Exa 切换、不做通用搜索引擎结果页爬取（baidu.com/s
  / bing.com/search 实测均被反爬降级为导航噪声），也不做站点独立适配
- 两个 TAVILY_API_KEY 都耗尽时：tavily_search 抛 TavilyQuotaExhaustedError，
  由 tasks.py 捕获后把任务标记为 failed + 明确的 error_message，让前端给用户明确提示
  （属于运维事件，提醒充值或等下月刷新即可，不做优雅降级）
"""

import logging
from urllib.parse import urlparse

from src.research_agent.nodes.filter import _extract_year
from src.research_agent.profiles import get_profile
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
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        domain_count[domain] = domain_count.get(domain, 0) + 1
    return {d for d, cnt in domain_count.items() if cnt >= min_count}


def search_node(state: ResearchState) -> dict:
    """执行搜索，收集候选结果"""
    plan = state["search_plan"]
    keywords = plan.get("keywords", [])
    target_domains = plan.get("target_domains", [])
    current_round = state.get("round", 1)

    profile = get_profile(state.get("profile_name"))

    # 域名合并：profile 定义的兜底域名 + LLM 针对本次主题推荐
    all_domains = list(set(list(profile.search_fallback_domains) + target_domains))

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

    all_candidates = _search_tavily(keywords, all_domains)

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
        "search 节点: %d 个关键词 → %d 条候选",
        len(keywords),
        len(all_candidates),
    )

    return {"candidates": all_candidates}


def _search_tavily(keywords: list[str], target_domains: list[str]) -> list[dict]:
    """对每个关键词调 Tavily 定向搜索，URL 去重后返回候选列表

    两 key 都耗尽时 tavily_search 抛 TavilyQuotaExhaustedError，不在此处吞异常——
    让它冒泡到 Celery 任务入口，由 tasks.py 标 failed + error_message。
    """
    from src.research_agent.tools.web_search import tavily_search

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        for r in tavily_search(query=kw, target_domains=target_domains, max_results=10):
            url = r["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title = r["title"]
            snippet = r["snippet"]
            # snippet 通常含发布年份，作为 URL/标题都无年份时的兜底
            year = _extract_year(url) or _extract_year(title) or _extract_year(snippet)
            candidates.append({
                "title": title,
                "url": url,
                "snippet": snippet,
                "full_text": "",  # fetcher 节点负责填充
                "source": _extract_domain(url),
                "content_type": _guess_content_type(url),
                "source_tier": "",
                "relevance_score": r.get("score", 0.0),
                "published_date": str(year) if year else "",
            })

    return candidates


def _cap_candidates_by_domain(candidates: list[dict], max_per_domain: int) -> list[dict]:
    """对候选池按域名限流，保留每个域名最靠前的 max_per_domain 条"""
    domain_count: dict[str, int] = {}
    result = []
    for c in candidates:
        domain = urlparse(c.get("url", "")).netloc.removeprefix("www.")
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
