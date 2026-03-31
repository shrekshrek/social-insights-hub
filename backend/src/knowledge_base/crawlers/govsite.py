"""gov.cn 互联网/数字经济/平台经济政策文件爬取

策略：
1. Crawl4AI 抓取 gov.cn 政策搜索页（三个关键词查询）
2. 从 Markdown 提取文章链接（过滤近 3 年，排除已见 URL）
3. Crawl4AI 逐篇抓取正文 → Markdown，存为 .md 文档
"""

import logging
import re
from datetime import datetime, timezone

from .base import BaseCrawler, CrawlSource

logger = logging.getLogger(__name__)

_CURRENT_YEAR = datetime.now(timezone.utc).year
_MIN_YEAR = _CURRENT_YEAR - 3

_SEARCH_URLS = [
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E4%BA%92%E8%81%94%E7%BD%91&t=zhengcelibrary",
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E6%95%B0%E5%AD%97%E7%BB%8F%E6%B5%8E&t=zhengcelibrary",
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E5%B9%B3%E5%8F%B0%E7%BB%8F%E6%B5%8E&t=zhengcelibrary",
]

_BASE_URL = "https://www.gov.cn"

# Markdown 链接模式：[标题](URL)
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")

# gov.cn 政策文章 URL 特征（排除首页/导航/搜索页）
_ARTICLE_PATH_PATTERN = re.compile(r"www\.gov\.cn/.+/\d{6}/")

# 从 URL 提取年份（YYYYMM 格式）
_YEAR_PATTERN = re.compile(r"/(20\d{2})\d{2}/")


class GovsiteCrawler(BaseCrawler):
    """gov.cn 政策文件爬取器"""

    source_type = "govsite"

    async def discover(self) -> list[CrawlSource]:
        seen: set[str] = set()
        article_links: list[tuple[str, str]] = []

        for search_url in _SEARCH_URLS:
            logger.info("[govsite] 抓取搜索页: %s", search_url)
            try:
                markdown = await self._crawl_url(search_url, query="政策文件")
                links = self._extract_article_links(markdown, seen)
                article_links.extend(links)
                logger.info("[govsite] 搜索页发现 %d 篇新文章", len(links))
            except Exception as e:
                logger.warning("[govsite] 搜索页抓取失败 %s: %s", search_url, e)

        logger.info("[govsite] 合计发现 %d 篇政策文章", len(article_links))

        sources = []
        for title, url in article_links:
            try:
                content = await self._crawl_url(url, query="互联网 数字经济 平台经济 政策")
                if not content.strip():
                    continue
                date_str = self._date_from_url(url)
                sources.append(
                    CrawlSource(
                        url=url,
                        title=title,
                        file_bytes=content.encode("utf-8"),
                        filename=f"govsite_{date_str}_{self._slug_from_url(url)}.md",
                        source_meta={"source": "govsite", "date": date_str},
                    )
                )
                logger.info("[govsite] 已抓取: %s", title)
            except Exception as e:
                logger.warning("[govsite] 跳过 %s: %s", url, e)

        return sources

    def _extract_article_links(
        self, markdown: str, seen: set[str]
    ) -> list[tuple[str, str]]:
        """从搜索结果 Markdown 提取近 3 年政策文章链接"""
        links = _LINK_PATTERN.findall(markdown)
        result = []
        for title, url in links:
            if url in seen:
                continue
            if not _ARTICLE_PATH_PATTERN.search(url):
                continue
            year = self._year_from_url(url)
            if year and year < _MIN_YEAR:
                continue
            # 补全相对 URL
            if url.startswith("/"):
                url = _BASE_URL + url
            seen.add(url)
            result.append((title.strip(), url))
        return result

    def _year_from_url(self, url: str) -> int | None:
        m = _YEAR_PATTERN.search(url)
        return int(m.group(1)) if m else None

    def _date_from_url(self, url: str) -> str:
        m = re.search(r"/(20\d{2})(\d{2})/", url)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        return "unknown"

    def _slug_from_url(self, url: str) -> str:
        """从 URL 末段提取短标识"""
        parts = url.rstrip("/").rsplit("/", 1)
        slug = parts[-1] if parts else "article"
        # 去掉 .htm / .html 后缀
        slug = re.sub(r"\.(html?|shtml)$", "", slug)
        return slug[:32]
