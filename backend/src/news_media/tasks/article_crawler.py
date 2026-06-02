"""Crawl4AI 新闻文章抓取器（同步版）

复用 knowledge_base.crawlers.base 的 Crawl4AI REST API 模式，
批量并发抓取新闻全文。

本模块由 Celery gevent worker 调用，用 requests + gevent.pool 并发；
gevent monkey-patch 让底层 socket 自动协作式让出。
"""

import logging

import requests
from gevent.pool import Pool

from src.config import settings

logger = logging.getLogger(__name__)

# 并发控制
_CONCURRENCY_LIMIT = 5
_PER_URL_TIMEOUT = 20.0


def _crawl_single_url(url: str) -> str | None:
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
        resp = requests.post(
            f"{settings.CRAWL4AI_BASE_URL}/crawl",
            json=payload,
            headers=headers,
            timeout=_PER_URL_TIMEOUT + 10,
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

    except (requests.RequestException, KeyError, ValueError) as e:
        logger.warning("Crawl4AI failed for %s: %s", url, e)
        return None


def crawl_articles(urls: list[str]) -> dict[str, str | None]:
    """批量并发抓取文章全文（同步版）

    Args:
        urls: 文章 URL 列表

    Returns:
        {url: full_text_or_None} 字典
    """
    if not urls:
        return {}

    pool = Pool(_CONCURRENCY_LIMIT)

    def _task(url: str) -> tuple[str, str | None]:
        try:
            return url, _crawl_single_url(url)
        except Exception as e:
            logger.warning("Unexpected error crawling %s: %s", url, e)
            return url, None

    pairs = list(pool.imap_unordered(_task, urls))
    results: dict[str, str | None] = dict(pairs)

    success = sum(1 for v in results.values() if v is not None)
    logger.info(
        "Crawl4AI batch: total=%d, success=%d, failed=%d",
        len(urls),
        success,
        len(urls) - success,
    )
    return results
