"""news_search 模块单元测试

测试重点：
- aggregator URL 去重逻辑（含 query string 归一化）
- source_tier 分类（tier1/tier2/tier3）
- DDG 失败降级（返回空列表，不抛异常）
- 双渠道并发合并结果
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.news_media.tasks.news_search.aggregator import (
    _normalize_url,
    classify_source_tier,
    search_news,
)


# ==================== classify_source_tier ====================


def test_tier1_sources():
    assert classify_source_tier("新华网") == "tier1"
    assert classify_source_tier("人民日报官方") == "tier1"
    assert classify_source_tier("澎湃新闻") == "tier1"


def test_tier2_sources():
    assert classify_source_tier("36氪") == "tier2"
    assert classify_source_tier("界面新闻") == "tier2"
    assert classify_source_tier("虎嗅网") == "tier2"


def test_tier3_fallback():
    assert classify_source_tier("百家号") == "tier3"
    assert classify_source_tier("未知来源") == "tier3"
    assert classify_source_tier("") == "tier3"


# ==================== _normalize_url ====================


def test_normalize_url_strips_query():
    url = "https://example.com/news/article-123?utm_source=baidu&from=news"
    assert _normalize_url(url) == "https://example.com/news/article-123"


def test_normalize_url_keeps_path():
    url = "https://xinhuanet.com/2026/04/05/news.html"
    assert _normalize_url(url) == "https://xinhuanet.com/2026/04/05/news.html"


def test_normalize_url_strips_trailing_slash():
    url = "https://example.com/news/"
    assert _normalize_url(url) == "https://example.com/news"


def test_normalize_url_handles_no_query():
    url = "https://example.com/article/123"
    assert _normalize_url(url) == "https://example.com/article/123"


# ==================== search_news (aggregator) ====================


@pytest.mark.asyncio
async def test_search_news_deduplicates_same_url():
    """同一 URL 来自两个渠道，只保留一条"""
    shared_url = "https://example.com/news/shared-article"
    baidu_result = [{
        "title": "共同文章", "url": shared_url, "snippet": "...",
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    ddg_result = [{
        "title": "共同文章", "url": shared_url, "snippet": "...",
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "duckduckgo",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)),
        patch("src.news_media.tasks.news_search.ddg_searcher.search_ddg_news", new=AsyncMock(return_value=ddg_result)),
    ):
        results = await search_news("测试", channels=["baidu", "duckduckgo"])

    assert len(results) == 1
    assert results[0]["url"] == shared_url


@pytest.mark.asyncio
async def test_search_news_merges_unique_articles():
    """两个渠道各有独立文章，合并后全部保留"""
    baidu_result = [{
        "title": "百度独有", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    ddg_result = [{
        "title": "DDG独有", "url": "https://36kr.com/a2", "snippet": None,
        "source_name": "36氪", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "duckduckgo",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)),
        patch("src.news_media.tasks.news_search.ddg_searcher.search_ddg_news", new=AsyncMock(return_value=ddg_result)),
    ):
        results = await search_news("测试", channels=["baidu", "duckduckgo"])

    assert len(results) == 2
    urls = {r["url"] for r in results}
    assert "https://xinhua.com/a1" in urls
    assert "https://36kr.com/a2" in urls


@pytest.mark.asyncio
async def test_search_news_adds_source_tier():
    """聚合后每条文章都有 source_tier 字段"""
    baidu_result = [{
        "title": "新华社报道", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华社", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)):
        results = await search_news("测试", channels=["baidu"])

    assert results[0]["source_tier"] == "tier1"


@pytest.mark.asyncio
async def test_search_news_ddg_failure_degrades_gracefully():
    """DDG 失败时只返回百度结果，不抛异常"""
    baidu_result = [{
        "title": "百度结果", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)),
        patch("src.news_media.tasks.news_search.ddg_searcher.search_ddg_news", new=AsyncMock(side_effect=Exception("DDG error"))),
    ):
        results = await search_news("测试", channels=["baidu", "duckduckgo"])

    assert len(results) == 1
    assert results[0]["source_name"] == "新华网"


@pytest.mark.asyncio
async def test_search_news_baidu_only_channel():
    """channels=["baidu"] 时不调用 DDG"""
    baidu_result = [{
        "title": "百度结果", "url": "https://example.com/a1", "snippet": None,
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)) as mock_baidu,
        patch("src.news_media.tasks.news_search.ddg_searcher.search_ddg_news", new=AsyncMock()) as mock_ddg,
    ):
        results = await search_news("测试", channels=["baidu"])

    mock_baidu.assert_called_once()
    mock_ddg.assert_not_called()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_news_url_dedup_with_query_string():
    """同一路径不同 query string 的 URL 视为重复"""
    baidu_result = [{
        "title": "文章A", "url": "https://example.com/news?id=1&from=baidu",
        "snippet": None, "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    ddg_result = [{
        "title": "文章A", "url": "https://example.com/news?id=1&utm=ddg",
        "snippet": None, "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "duckduckgo",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", new=AsyncMock(return_value=baidu_result)),
        patch("src.news_media.tasks.news_search.ddg_searcher.search_ddg_news", new=AsyncMock(return_value=ddg_result)),
    ):
        results = await search_news("测试", channels=["baidu", "duckduckgo"])

    # query 去掉后路径相同，应去重
    assert len(results) == 1
