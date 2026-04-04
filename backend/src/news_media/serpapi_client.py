"""SerpAPI Baidu News 客户端

封装 SerpAPI Baidu News API，返回结构化的新闻搜索结果。
参考：https://serpapi.com/baidu-news-api
"""

import logging
from datetime import datetime, timezone

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

SERPAPI_BASE_URL = "https://serpapi.com/search"

# 中国主流新闻来源分层
SOURCE_TIERS: dict[str, list[str]] = {
    "tier1": [
        "新华网", "新华社", "人民日报", "人民网", "央视", "央视网", "CCTV",
        "中国日报", "经济日报", "光明日报", "环球时报", "中国新闻网", "澎湃新闻",
        "新华每日电讯", "参考消息", "半月谈",
    ],
    "tier2": [
        "第一财经", "财新", "财新网", "21世纪经济报道", "每日经济新闻",
        "界面新闻", "36氪", "虎嗅", "新浪财经", "腾讯新闻", "腾讯科技",
        "网易新闻", "网易科技", "搜狐新闻", "凤凰网", "凤凰财经",
        "南方都市报", "南方周末", "北京青年报", "新京报", "证券时报",
        "中国证券报", "上海证券报", "经济观察报", "IT之家", "钛媒体",
    ],
}


def classify_source_tier(source_name: str) -> str:
    """根据来源名称判断权威度分层"""
    for tier, sources in SOURCE_TIERS.items():
        if any(name in source_name for name in sources):
            return tier
    return "tier3"


def _parse_relative_date(date_str: str) -> datetime | None:
    """尝试解析 SerpAPI 返回的相对日期（如 '5分钟前', '昨天', '3天前'）"""
    if not date_str:
        return None
    now = datetime.now(timezone.utc)
    try:
        if "分钟前" in date_str:
            minutes = int("".join(c for c in date_str if c.isdigit()) or "0")
            from datetime import timedelta
            return now - timedelta(minutes=minutes)
        if "小时前" in date_str:
            hours = int("".join(c for c in date_str if c.isdigit()) or "0")
            from datetime import timedelta
            return now - timedelta(hours=hours)
        if "天前" in date_str:
            days = int("".join(c for c in date_str if c.isdigit()) or "0")
            from datetime import timedelta
            return now - timedelta(days=days)
        if "昨天" in date_str:
            from datetime import timedelta
            return now - timedelta(days=1)
        if "前天" in date_str:
            from datetime import timedelta
            return now - timedelta(days=2)
    except (ValueError, TypeError):
        pass
    return None


async def search_baidu_news(
    query: str,
    max_results: int = 10,
    sort_by_time: bool = False,
) -> list[dict]:
    """调用 SerpAPI Baidu News 搜索

    Args:
        query: 搜索关键词
        max_results: 最大结果数（SerpAPI 单次最多 50）
        sort_by_time: True=按时间排序, False=按相关性排序

    Returns:
        结构化文章列表，每个包含 title, url, snippet, source_name, source_tier,
        published_at, image_url, raw_data
    """
    api_key = settings.SERPAPI_API_KEY
    if not api_key:
        raise ValueError("SERPAPI_API_KEY not configured")

    articles: list[dict] = []
    seen_urls: set[str] = set()
    results_per_page = min(max_results, 50)
    pages_needed = (max_results + results_per_page - 1) // results_per_page

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page_idx in range(pages_needed):
            params = {
                "engine": "baidu_news",
                "q": query,
                "api_key": api_key,
                "rn": results_per_page,
                "pn": page_idx * results_per_page,
                "rtt": "4" if sort_by_time else "1",
            }

            resp = await client.get(SERPAPI_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            organic_results = data.get("organic_results", [])
            if not organic_results:
                break

            for item in organic_results:
                url = item.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                source_name = item.get("source", "")
                articles.append({
                    "url": url,
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet"),
                    "source_name": source_name,
                    "source_tier": classify_source_tier(source_name),
                    "published_at": _parse_relative_date(item.get("date", "")),
                    "image_url": item.get("thumbnail"),
                    "raw_data": item,
                })

                if len(articles) >= max_results:
                    break

            if len(articles) >= max_results:
                break

    logger.info("SerpAPI Baidu News: query=%r, results=%d", query, len(articles))
    return articles
