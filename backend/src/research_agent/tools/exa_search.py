"""Exa 定向搜索工具

同步调用（gevent 兼容）。
- category="research_paper" 偏向学术/报告类内容
- include_domains 支持最多 1200 个域名（Tavily 限 300）
- text=True 直接返回全文（最多 20k chars），可省略 fetcher 节点抓取
"""

import logging

from src.config import get_settings

logger = logging.getLogger(__name__)


def exa_search(
    query: str,
    target_domains: list[str],
    max_results: int = 10,
) -> list[dict]:
    """Exa 定向搜索，返回候选列表（含全文）

    Parameters
    ----------
    query : 搜索关键词
    target_domains : include_domains 定向搜索域名
    max_results : 最大结果数

    Returns
    -------
    list[dict] : [{title, url, snippet, full_text, score}]
        full_text 为 Exa 直接返回的全文（最多 20k chars），
        analyzer 节点可直接使用，无需再走 fetcher。
    """
    from exa_py import Exa

    settings = get_settings()
    if not settings.EXA_API_KEY:
        logger.warning("EXA_API_KEY 未配置，跳过搜索")
        return []

    if not target_domains:
        logger.warning("target_domains 为空，跳过搜索")
        return []

    client = Exa(api_key=settings.EXA_API_KEY)

    try:
        resp = client.search_and_contents(
            query,
            category="research paper",
            include_domains=target_domains,
            num_results=max_results,
            text=True,           # 返回最多 20k chars 全文
        )
        results = resp.results or []

        return [
            {
                "title": r.title or "",
                "url": r.url or "",
                "snippet": (r.text or "")[:500],   # filter 节点用摘要
                "full_text": r.text or "",           # analyzer 节点用全文
                "score": r.score or 0.0,
                "published_date": r.published_date or "",
            }
            for r in results
        ]
    except Exception:
        logger.exception("Exa 搜索失败: query=%s", query)
        return []
