"""Crawl4AI 搜索工具

当 Tavily 候选结果不足时，通过 Crawl4AI 渲染 Baidu/Bing 搜索结果页来补充候选。
与 Tavily 不同，这里不限制 include_domains，走全网搜索，偏向报告类内容。
"""

import logging
import re
from urllib.parse import quote_plus, urlparse

import httpx

from src.config import get_settings
from src.research_agent.config import FETCH_HTML_TIMEOUT

logger = logging.getLogger(__name__)

# 搜索引擎自身域名，提取候选时过滤掉
_ENGINE_DOMAINS = {
    "baidu.com", "bing.com", "google.com",
    "microsoft.com", "sogou.com", "so.com",
    "sm.cn", "360.cn",
}

# Baidu 搜索 URL：偏向 PDF 报告，每页 20 条
_BAIDU_SEARCH_URL = "https://www.baidu.com/s?wd={query}&rn=20&f=3"
# Bing 国际版（备用，适合英文报告）
_BING_SEARCH_URL = "https://www.bing.com/search?q={query}&count=20"


def crawl4ai_search(query: str, max_results: int = 15) -> list[dict]:
    """使用 Crawl4AI 渲染搜索结果页，返回候选列表

    优先使用 Baidu（中文报告友好），失败时切换 Bing。

    Parameters
    ----------
    query : 搜索关键词
    max_results : 最多返回条目数

    Returns
    -------
    list[dict] : [{title, url, snippet, source, content_type, source_tier, relevance_score}]
    """
    settings = get_settings()
    if not settings.CRAWL4AI_BASE_URL:
        logger.warning("CRAWL4AI_BASE_URL 未配置，跳过 Crawl4AI 搜索")
        return []

    candidates = _search_via_engine(
        query=query,
        search_url=_BAIDU_SEARCH_URL.format(query=quote_plus(query)),
        max_results=max_results,
    )

    # Baidu 失败或结果过少时，尝试 Bing
    if len(candidates) < 3:
        logger.info("Baidu 结果不足（%d），切换 Bing 补充", len(candidates))
        bing_candidates = _search_via_engine(
            query=query,
            search_url=_BING_SEARCH_URL.format(query=quote_plus(query)),
            max_results=max_results,
        )
        seen = {c["url"] for c in candidates}
        for c in bing_candidates:
            if c["url"] not in seen:
                candidates.append(c)
                seen.add(c["url"])

    return candidates[:max_results]


def _search_via_engine(query: str, search_url: str, max_results: int) -> list[dict]:
    """爬取指定搜索 URL，提取结果链接"""
    settings = get_settings()
    base_url = settings.CRAWL4AI_BASE_URL

    payload = {
        "urls": [search_url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": FETCH_HTML_TIMEOUT * 1000,
        },
    }
    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        with httpx.Client(timeout=FETCH_HTML_TIMEOUT + 15) as client:
            resp = client.post(f"{base_url}/crawl", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            return []

        result = results[0]

        # 优先从 links.external 提取（结构化，比解析 markdown 可靠）
        external_links = result.get("links", {}).get("external", [])
        candidates = _links_to_candidates(external_links, max_results)

        # 回退：从 markdown 中正则提取 [title](url)
        if len(candidates) < 3:
            markdown = result.get("markdown", {})
            text = markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
            md_candidates = _parse_markdown_links(text, max_results)
            seen = {c["url"] for c in candidates}
            for c in md_candidates:
                if c["url"] not in seen:
                    candidates.append(c)
                    seen.add(c["url"])

        logger.info(
            "Crawl4AI 搜索 [%s]: '%s' → %d 条",
            urlparse(search_url).netloc,
            query,
            len(candidates),
        )
        return candidates[:max_results]

    except Exception:
        logger.warning("Crawl4AI 搜索失败: url=%s", search_url, exc_info=True)
        return []


def _links_to_candidates(links: list[dict], max_results: int) -> list[dict]:
    """从 Crawl4AI links 数组提取候选（过滤搜索引擎内部链接）"""
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for link in links:
        url = link.get("href", "").strip()
        title = link.get("text", "").strip()

        if not url or not title or len(title) < 4:
            continue
        if url in seen_urls:
            continue

        domain = _extract_domain(url)
        if any(d in domain for d in _ENGINE_DOMAINS):
            continue

        seen_urls.add(url)
        candidates.append(_make_candidate(title, url))

        if len(candidates) >= max_results:
            break

    return candidates


def _parse_markdown_links(text: str, max_results: int) -> list[dict]:
    """从 markdown 文本中提取 [title](url) 格式的链接"""
    # 标题长度 5-200 字符，URL 必须以 http 开头
    pattern = r"\[([^\]]{5,200})\]\((https?://[^\)]{10,500})\)"
    matches = re.findall(pattern, text)

    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for title, url in matches:
        url = url.strip()
        if url in seen_urls:
            continue
        domain = _extract_domain(url)
        if any(d in domain for d in _ENGINE_DOMAINS):
            continue
        seen_urls.add(url)
        candidates.append(_make_candidate(title.strip(), url))
        if len(candidates) >= max_results:
            break

    return candidates


def _make_candidate(title: str, url: str) -> dict:
    domain = _extract_domain(url)
    return {
        "title": title[:200],
        "url": url,
        "snippet": "",
        "source": domain,
        "content_type": "pdf" if url.lower().endswith(".pdf") else "html",
        "source_tier": "",       # filter 节点负责标注
        "relevance_score": 0.4,  # 低于 Tavily 结果的默认分（Tavily 有语义评分）
    }


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
