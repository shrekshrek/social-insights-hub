"""Crawl4AI 新闻文章抓取器

复用 knowledge_base.crawlers.base._crawl_url 的 Crawl4AI REST API 模式，
批量并发抓取新闻全文。
"""

import asyncio
import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# 并发控制
_CONCURRENCY_LIMIT = 5
_PER_URL_TIMEOUT = 20.0


async def _crawl_single_url(url: str) -> str | None:
    """调用 Crawl4AI REST API 抓取单个 URL 的正文

    Returns:
        fit_markdown 正文，或 None 如果失败
    """
    payload: dict = {
        "urls": [url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": int(_PER_URL_TIMEOUT * 1000),
        },
    }

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=_PER_URL_TIMEOUT + 10) as client:
            resp = await client.post(
                f"{settings.CRAWL4AI_BASE_URL}/crawl",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning("Crawl4AI empty result: %s", url)
            return None

        markdown = results[0].get("markdown", {})
        content = markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
        if not content.strip():
            logger.warning("Crawl4AI empty content: %s", url)
            return None

        return content

    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning("Crawl4AI failed for %s: %s", url, e)
        return None


async def crawl_articles(urls: list[str]) -> dict[str, str | None]:
    """批量并发抓取文章全文

    Args:
        urls: 文章 URL 列表

    Returns:
        {url: full_text_or_None} 字典
    """
    semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
    results: dict[str, str | None] = {}

    async def _task(url: str) -> None:
        async with semaphore:
            results[url] = await _crawl_single_url(url)

    await asyncio.gather(*[_task(url) for url in urls], return_exceptions=True)

    success = sum(1 for v in results.values() if v is not None)
    logger.info(
        "Crawl4AI batch: total=%d, success=%d, failed=%d",
        len(urls), success, len(urls) - success,
    )
    return results
