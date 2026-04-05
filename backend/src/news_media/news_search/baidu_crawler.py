"""百度新闻搜索爬虫

通过 Crawl4AI REST API 爬取百度新闻搜索结果页，返回结构化文章列表。
目标 URL：https://news.baidu.com/ns?word={query}&rn={n}&tn=news
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_BAIDU_NEWS_URL = "https://news.baidu.com/ns"


def _parse_baidu_date(date_str: str) -> datetime | None:
    """解析百度新闻返回的相对/绝对日期字符串"""
    if not date_str:
        return None
    now = datetime.now(timezone.utc)
    try:
        if "分钟前" in date_str:
            minutes = int(re.search(r"\d+", date_str).group())
            return now - timedelta(minutes=minutes)
        if "小时前" in date_str:
            hours = int(re.search(r"\d+", date_str).group())
            return now - timedelta(hours=hours)
        if "天前" in date_str:
            days = int(re.search(r"\d+", date_str).group())
            return now - timedelta(days=days)
        if "昨天" in date_str:
            return now - timedelta(days=1)
        if "前天" in date_str:
            return now - timedelta(days=2)
        # 尝试解析 "YYYY年MM月DD日" 或 "MM月DD日"
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        m = re.search(r"(\d{1,2})月(\d{1,2})日", date_str)
        if m:
            return datetime(now.year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        pass
    return None


def _extract_articles_from_markdown(markdown: str, max_results: int) -> list[dict]:
    """从 fit_markdown 内容中提取文章列表

    百度新闻搜索结果页结构相对稳定，每条结果包含：
    - 标题（链接文字）
    - URL
    - 来源（媒体名称）
    - 时间
    - 摘要
    """
    articles: list[dict] = []
    seen_urls: set[str] = set()

    # 匹配 markdown 链接: [标题](url)
    # 百度新闻结果页中文章标题通常是链接
    link_pattern = re.compile(r"\[([^\[\]]{5,200})\]\((https?://[^\s\)]+)\)")

    # 来源和时间通常跟在链接后，格式多样，用宽松模式提取
    source_pattern = re.compile(r"([^\n\|]{2,30})\s*[|\-·]\s*(\d{1,2}[小时分钟天前昨前年月日]+[前]?)")

    lines = markdown.split("\n")
    i = 0
    while i < len(lines) and len(articles) < max_results:
        line = lines[i].strip()
        link_match = link_pattern.search(line)
        if link_match:
            title = link_match.group(1).strip()
            url = link_match.group(2).strip()

            # 过滤非新闻链接（百度导航、广告等）
            if url in seen_urls or not _is_news_url(url) or len(title) < 5:
                i += 1
                continue
            seen_urls.add(url)

            # 向下找来源和时间（通常在紧接的几行）
            source_name = ""
            published_at = None
            snippet = ""
            for j in range(i + 1, min(i + 5, len(lines))):
                ctx = lines[j].strip()
                if not ctx:
                    continue
                src_match = source_pattern.search(ctx)
                if src_match and not source_name:
                    source_name = src_match.group(1).strip()
                    published_at = _parse_baidu_date(src_match.group(2))
                elif not snippet and len(ctx) > 10 and not ctx.startswith("["):
                    snippet = ctx[:300]

            articles.append({
                "title": title,
                "url": url,
                "snippet": snippet or None,
                "source_name": source_name or "未知来源",
                "published_at": published_at,
                "image_url": None,
                "raw_data": {"title": title, "url": url, "source": source_name},
                "search_source": "baidu",
            })
        i += 1

    return articles


def _is_news_url(url: str) -> bool:
    """简单过滤非新闻 URL（百度自身页面、广告等）"""
    skip_domains = ("baidu.com", "bdstatic.com", "baiducontent.com")
    return not any(d in url for d in skip_domains)


async def search_baidu_news(query: str, max_results: int = 10) -> list[dict]:
    """通过 Crawl4AI 爬取百度新闻搜索结果

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，每条含 title, url, snippet, source_name, published_at,
        image_url, raw_data, search_source="baidu"
    """
    encoded_query = quote(query)
    target_url = f"{_BAIDU_NEWS_URL}?word={encoded_query}&rn={min(max_results, 50)}&tn=news&cl=2&ie=utf-8"

    payload: dict = {
        "urls": [target_url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": 20000,
        },
    }

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.CRAWL4AI_BASE_URL}/crawl",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning("Crawl4AI: 百度新闻爬取返回空结果, query=%r", query)
            return []

        markdown = results[0].get("markdown", {})
        content = markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
        if not content.strip():
            logger.warning("Crawl4AI: 百度新闻内容为空, query=%r", query)
            return []

        articles = _extract_articles_from_markdown(content, max_results)
        logger.info("百度新闻: query=%r, 提取文章数=%d", query, len(articles))
        return articles

    except httpx.HTTPError as e:
        logger.error("Crawl4AI 请求失败: %s", e)
        raise
