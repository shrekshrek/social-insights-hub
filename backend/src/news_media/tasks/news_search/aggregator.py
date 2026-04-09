"""新闻搜索双渠道聚合器

并发调用百度新闻（Crawl4AI）和 DuckDuckGo，按 URL 去重合并，
返回统一结构的文章列表（含 source_tier 分类）。
"""

import asyncio
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 中国新闻来源权威度分层
_SOURCE_TIERS: dict[str, list[str]] = {
    "tier1": [
        "新华网", "新华社", "人民日报", "人民网", "央视", "央视网", "CCTV",
        "中国日报", "经济日报", "光明日报", "环球时报", "中国新闻网", "澎湃新闻",
        "新华每日电讯", "参考消息", "半月谈",
    ],
    "tier2": [
        "第一财经", "财新", "财新网", "21世纪经济报道", "每日经济新闻",
        "界面新闻", "36氪", "虎嗅", "新浪财经", "新浪科技", "腾讯新闻", "腾讯科技",
        "网易新闻", "网易科技", "搜狐新闻", "凤凰网", "凤凰财经",
        "南方都市报", "南方周末", "北京青年报", "新京报", "证券时报",
        "中国证券报", "上海证券报", "经济观察报", "IT之家", "钛媒体",
        # 省级党报 / 地方主流（采样命中）
        "上观新闻", "解放日报", "新民晚报", "文汇报",
        "极目新闻", "湖北日报", "楚天都市报",
        "海报新闻", "大众日报", "齐鲁晚报",
        "红星新闻", "成都商报", "封面新闻",
        "潇湘晨报", "扬子晚报", "现代快报",
    ],
}


def classify_source_tier(source_name: str) -> str:
    """根据来源名称判断权威度分层"""
    for tier, sources in _SOURCE_TIERS.items():
        if any(name in source_name for name in sources):
            return tier
    return "tier3"


def _normalize_url(url: str) -> str:
    """URL 归一化，去除常见追踪参数，用于去重"""
    try:
        parsed = urlparse(url)
        # 去除 query string 中的追踪参数
        if parsed.query:
            # 保留路径，去掉 query（百度新闻文章 URL 通常 path 就够去重）
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        return url.rstrip("/")
    except Exception:
        return url


async def search_news(
    query: str,
    max_results: int = 50,
    channels: list[str] | None = None,
) -> list[dict]:
    """双渠道并发搜索，URL 去重合并，附加 source_tier

    Args:
        query: 搜索关键词
        max_results: 每个渠道的最大结果数
        channels: 启用的渠道列表，默认 ["baidu", "duckduckgo"]
                  probe 阶段传 ["baidu"]，collect 阶段传 ["baidu", "duckduckgo"]

    Returns:
        去重后的文章列表，每条含标准字段 + source_tier + search_source
    """
    if channels is None:
        channels = ["baidu", "duckduckgo"]

    tasks = []
    if "baidu" in channels:
        from src.news_media.tasks.news_search.baidu_crawler import search_baidu_news
        tasks.append(search_baidu_news(query, max_results=max_results))
    if "duckduckgo" in channels:
        from src.news_media.tasks.news_search.ddg_searcher import search_ddg_news
        tasks.append(search_ddg_news(query, max_results=max_results))

    if not tasks:
        return []

    # 并发执行，DDG 失败不影响百度
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[dict] = []
    for result in raw_results:
        if isinstance(result, Exception):
            logger.warning("搜索渠道异常（已忽略）: %s", result)
            continue
        all_articles.extend(result)

    # URL 归一化去重（保留先出现的）
    seen_normalized: set[str] = set()
    deduped: list[dict] = []
    for article in all_articles:
        norm = _normalize_url(article["url"])
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)

        # 补充 source_tier
        article["source_tier"] = classify_source_tier(article.get("source_name", ""))
        deduped.append(article)

    logger.info(
        "聚合搜索: query=%r, channels=%s, 原始=%d, 去重后=%d",
        query, channels, len(all_articles), len(deduped),
    )
    return deduped
