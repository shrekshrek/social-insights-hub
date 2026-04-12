"""Tavily 定向搜索工具

同步调用（gevent 兼容），始终使用 include_domains 定向搜索。
只搜索指定权威域名，不做开放全网搜索。
"""

import logging

from tavily import TavilyClient

from src.config import get_settings

logger = logging.getLogger(__name__)


def tavily_search(
    query: str,
    target_domains: list[str],
    max_results: int = 10,
) -> list[dict]:
    """Tavily 定向搜索，返回候选列表

    Parameters
    ----------
    query : 搜索关键词
    target_domains : include_domains 定向搜索域名（必须）
    max_results : 最大结果数

    Returns
    -------
    list[dict] : [{title, url, snippet, score}]
    """
    settings = get_settings()
    if not settings.TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY 未配置，跳过搜索")
        return []

    if not target_domains:
        logger.warning("target_domains 为空，跳过搜索")
        return []

    client = TavilyClient(api_key=settings.TAVILY_API_KEY)

    try:
        resp = client.search(
            query=query,
            include_domains=target_domains,
            max_results=max_results,
            search_depth="advanced",
        )
        results = resp.get("results", [])

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "score": r.get("score", 0.0),
            }
            for r in results
        ]
    except Exception:
        logger.exception("Tavily 搜索失败: query=%s", query)
        return []
