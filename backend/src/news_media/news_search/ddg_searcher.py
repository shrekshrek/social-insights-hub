"""DuckDuckGo 新闻搜索封装

使用 duckduckgo_search 库（ddgs）搜索新闻，region="cn-zh" 优先中文结果。
DDG 会限速，采用指数退避重试，失败时返回空列表（不影响主流程）。
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # 秒


def _parse_ddg_date(date_str: str | None) -> datetime | None:
    """解析 DDG 返回的日期字符串（ISO 格式或相对时间）"""
    if not date_str:
        return None
    try:
        # DDG 通常返回 ISO 格式
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    return None


async def search_ddg_news(query: str, max_results: int = 50) -> list[dict]:
    """DuckDuckGo 新闻搜索

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，每条含 title, url, snippet, source_name, published_at,
        image_url, raw_data, search_source="duckduckgo"
        DDG 限速或失败时返回空列表。
    """
    for attempt in range(_MAX_RETRIES):
        try:
            # 在线程池中运行同步 ddgs 调用（避免阻塞事件循环）
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                _ddg_news_sync,
                query,
                max_results,
            )
            logger.info("DuckDuckGo: query=%r, 结果数=%d", query, len(results))
            return results

        except Exception as e:
            err_name = type(e).__name__
            if "Ratelimit" in err_name or "ratelimit" in str(e).lower():
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "DDG 限速 (attempt %d/%d)，%.1fs 后重试: %s",
                    attempt + 1, _MAX_RETRIES, delay, e,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
            else:
                logger.warning("DDG 搜索失败，降级返回空列表: %s", e)
                return []

    logger.warning("DDG 多次限速后放弃，query=%r", query)
    return []


def _ddg_news_sync(query: str, max_results: int) -> list[dict]:
    """同步执行 DDG 搜索（在线程池中调用）"""
    from duckduckgo_search import DDGS

    raw_results = DDGS().news(
        query,
        region="cn-zh",
        max_results=max_results,
    )

    articles: list[dict] = []
    for item in raw_results or []:
        url = item.get("url", "")
        if not url:
            continue
        articles.append({
            "title": item.get("title", ""),
            "url": url,
            "snippet": item.get("body") or None,
            "source_name": item.get("source", "未知来源"),
            "published_at": _parse_ddg_date(item.get("date")),
            "image_url": item.get("image") or None,
            "raw_data": item,
            "search_source": "duckduckgo",
        })
    return articles
