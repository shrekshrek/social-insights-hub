"""Bing 新闻搜索爬虫

通过 Crawl4AI REST API 爬取 Bing 新闻搜索结果页，返回结构化文章列表。
目标 URL: https://www.bing.com/news/search?q={query}&setmkt=en-US

## 关键设计：为何用 en-US 而非 zh-CN

实测 Bing 的 zh-CN / cn.bing.com 对无头浏览器有明显的反爬屏障——
返回的不是新闻搜索结果，而是 Bing 中文首页（含每日壁纸 + Microsoft 365 产品推广 nav，
推广链接带 WT.mc_id=O16_BingHP 追踪参数，不是新闻）。

en-US 则正常返回真实新闻结果（Engadget / Forbes / Digital Trends / Reuters 等国际英文媒体）。
这正好匹配 Bing 对本项目的定位——**英文国际媒体补充**，覆盖百度/搜狗的盲区，
而非再做一个中文主力渠道（中文新闻交给百度+搜狗）。

## 解析策略

Bing 新闻页的新闻卡片在 markdown 转换后，标题 + 文章链接会保留为
`[title](article_url)` 形式；元数据（source / 时间 / 摘要）散落在相邻纯文本节点，
正则提取成本高且不稳定。本爬虫采用"markdown link 为主"的提取：
以 title + article url 为核心数据，source_name 用文章域名兜底（足以支持
source_tier 分类与下游去重），snippet / published_at 留空，由 collect 阶段
抓全文时补齐。

架构上与 baidu_crawler / sogou_crawler 的产出格式完全一致（search_source="bing"），
aggregator 统一处理去重和 tier 分类，无需特殊处理。
"""

import html as html_lib
import logging
import re
from urllib.parse import quote, urlparse

import requests

from src.config import settings
from src.news_media.tasks.news_search._crawl4ai_client import fetch_via_crawl4ai

logger = logging.getLogger(__name__)

_BING_NEWS_URL = "https://www.bing.com/news/search"

# Bing 及 Microsoft 生态产品域名（搜索引擎内部/推广链接，过滤掉）
# 实测 Bing 新闻页 nav/sidebar 会塞入一堆 Microsoft 产品促销链接（WT.mc_id=O16_BingHP 追踪参数为标志），
# 必须在域名层面过滤，否则会把 PowerPoint/Excel/Outlook/OneNote 这些当"新闻"抓回来
_BING_INTERNAL_DOMAINS = {
    "bing.com",
    "microsoft.com",
    "microsoft365.com",
    "office.com",
    "outlook.com",
    "outlook.live.com",
    "onenote.com",
    "onedrive.live.com",
    "calendar.live.com",
    "sway.office.com",
    "msn.com",
    "live.com",
    "go.microsoft.com",
    "microsoftstart.msn.com",
    "skype.com",
    "xbox.com",
}

# markdown link 形式：[title](url)，title 长度 5-200 字，URL 以 http(s) 开头
_MD_LINK_RE = re.compile(r"\[([^\]]{5,200})\]\((https?://[^\)]{10,500})\)")


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_internal_link(url: str) -> bool:
    """过滤 Bing 自身 / Microsoft 生态页面链接"""
    domain = _extract_domain(url)
    return any(d in domain for d in _BING_INTERNAL_DOMAINS)


def _extract_articles_from_markdown(markdown: str, max_results: int) -> list[dict]:
    """从 crawl4ai 返回的 markdown 中提取 [title](url) 候选

    过滤掉 Bing 自身页面链接（导航/帮助/登录等），只保留指向外部新闻源的链接。
    标题长度/URL 长度的下限在正则中已约束。
    """
    articles: list[dict] = []
    seen_urls: set[str] = set()

    for match in _MD_LINK_RE.finditer(markdown):
        if len(articles) >= max_results:
            break

        title = html_lib.unescape(match.group(1).strip())
        url = match.group(2).strip()

        if len(title) < 5 or url in seen_urls:
            continue
        if _is_internal_link(url):
            continue

        seen_urls.add(url)
        domain = _extract_domain(url)
        articles.append({
            "title": title[:300],
            "url": url,
            "snippet": None,
            "source_name": domain or "未知来源",
            "published_at": None,
            "image_url": None,
            "raw_data": {"title": title, "url": url, "source": domain},
            "search_source": "bing",
        })

    return articles


def search_bing_news(query: str, max_results: int = 10) -> list[dict]:
    """通过 Crawl4AI 爬取 Bing 新闻搜索结果（同步版）

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，与 baidu/sogou 格式一致；每条含 title, url, snippet=None,
        source_name（域名）, published_at=None, image_url=None, raw_data,
        search_source="bing"

        probe 阶段仅需 title/url/snippet 支撑 LLM 判断相关性，source_name 用域名
        已足够 source_tier 分类；完整元数据在 collect 阶段抓全文时补齐。
    """
    if not settings.CRAWL4AI_BASE_URL:
        logger.warning("CRAWL4AI_BASE_URL 未配置，跳过 Bing 新闻搜索")
        return []

    # 关键：setmkt=en-US
    # zh-CN / cn.bing.com 对无头浏览器会重定向到 Bing 中文首页（纯推广内容，0 条新闻）；
    # en-US 才返回真实新闻搜索结果。这也正好匹配 Bing 对本项目的定位——
    # 英文国际媒体补充（百度/搜狗覆盖不到的 Engadget / Forbes / Reuters 等），而非中文主力
    encoded_query = quote(query)
    target_url = f"{_BING_NEWS_URL}?q={encoded_query}&setmkt=en-US"

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        with requests.Session() as session:
            result = fetch_via_crawl4ai(
                session, target_url, headers, page_timeout=20000
            )

        if not result:
            logger.warning("Bing 新闻: crawl4ai 无结果, query=%r", query)
            return []

        markdown_obj = result.get("markdown") or {}
        markdown_text = (
            markdown_obj.get("fit_markdown")
            or markdown_obj.get("raw_markdown")
            or ""
        )

        if not markdown_text.strip():
            logger.warning("Bing 新闻: markdown 为空, query=%r", query)
            return []

        articles = _extract_articles_from_markdown(markdown_text, max_results)
        logger.info("Bing 新闻: query=%r, 提取文章数=%d", query, len(articles))
        return articles

    except requests.RequestException as e:
        logger.error("Crawl4AI 请求失败 (Bing): %s", e)
        raise
