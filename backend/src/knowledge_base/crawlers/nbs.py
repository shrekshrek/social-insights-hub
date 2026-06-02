"""国家统计局月度新闻发布爬取

策略：
1. Crawl4AI 抓取月度新闻发布列表页，提取文章链接
2. 过滤含核心指标关键词的月报（CPI、GDP、社零等）
3. Crawl4AI 逐篇抓取正文 → Markdown，存为 .md 文档
"""

import logging
import re

from .base import BaseCrawler, CrawlSource

logger = logging.getLogger(__name__)

_INDEX_URL = "https://www.stats.gov.cn/sj/zxfb/"
_BASE_URL = "https://www.stats.gov.cn"

# 只抓含这些关键词的月报，过滤季报/年报/专题
_KEYWORDS = [
    "居民消费价格",
    "工业生产者出厂价格",
    "国内生产总值",
    "社会消费品零售",
    "全国居民人均",
    "国民经济",
]

# Markdown 链接模式：[标题](URL) 或 [标题](URL "title")，只取 URL 部分
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)")


class NBSCrawler(BaseCrawler):
    """国家统计局月度新闻发布爬取器"""

    source_type = "nbs"

    async def discover(self) -> list[CrawlSource]:
        logger.info("[nbs] 抓取月度发布列表: %s", _INDEX_URL)
        try:
            markdown = await self._crawl_url(_INDEX_URL)
        except Exception as e:
            logger.error("[nbs] 列表页抓取失败: %s", e, exc_info=True)
            return []

        article_links = self._extract_article_links(markdown)
        logger.info("[nbs] 发现相关月报 %d 篇", len(article_links))

        sources = []
        for title, url in article_links:
            try:
                content = await self._crawl_url(url)
                if not content.strip():
                    logger.warning("[nbs] 内容为空: %s", url)
                    continue
                date_str = self._date_from_url(url)
                sources.append(
                    CrawlSource(
                        url=url,
                        title=title,
                        file_bytes=content.encode("utf-8"),
                        filename=f"nbs_{date_str}.md",
                        source_meta={"source": "nbs", "date": date_str},
                    )
                )
                logger.info("[nbs] 已抓取: %s", title)
            except Exception as e:
                logger.warning("[nbs] 跳过 %s: %s", url, e, exc_info=True)

        return sources

    def _extract_article_links(self, markdown: str) -> list[tuple[str, str]]:
        """从列表页 Markdown 提取含关键词的文章链接"""
        links = _LINK_PATTERN.findall(markdown)
        result = []
        seen: set[str] = set()
        for title, url in links:
            if url in seen:
                continue
            if any(kw in title for kw in _KEYWORDS):
                # 补全相对 URL
                if url.startswith("/"):
                    url = _BASE_URL + url
                seen.add(url)
                result.append((title.strip(), url))
        return result

    def _date_from_url(self, url: str) -> str:
        m = re.search(r"(20\d{2})(\d{2})", url)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        return "unknown"
