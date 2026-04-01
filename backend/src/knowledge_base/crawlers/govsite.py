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
    # 基础互联网/数字经济
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E4%BA%92%E8%81%94%E7%BD%91&t=zhengcelibrary",        # 互联网
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E6%95%B0%E5%AD%97%E7%BB%8F%E6%B5%8E&t=zhengcelibrary",  # 数字经济
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E5%B9%B3%E5%8F%B0%E7%BB%8F%E6%B5%8E&t=zhengcelibrary",  # 平台经济
    # 社媒/营销相关
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E4%BA%92%E8%81%94%E7%BD%91%E5%B9%BF%E5%91%8A&t=zhengcelibrary",  # 互联网广告
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E7%94%B5%E5%AD%90%E5%95%86%E5%8A%A1&t=zhengcelibrary",          # 电子商务
    "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?q=%E6%B6%88%E8%B4%B9%E8%80%85%E6%9D%83%E7%9B%8A&t=zhengcelibrary", # 消费者权益
]

_BASE_URL = "https://www.gov.cn"

# Markdown 链接模式：[标题](URL) 或 [标题](URL "title")，只取 URL 部分
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)")

# gov.cn 政策文章 URL 特征（排除首页/导航/搜索页）
_ARTICLE_PATH_PATTERN = re.compile(r"www\.gov\.cn/.+/\d{6}/")

# 标题黑名单关键词（过滤与社媒营销无关的政策）
_TITLE_BLACKLIST = re.compile(
    r"工业互联网|农药|药品|医疗器械|气象|期货|跨境电子商务|金融消费者|金融机构消费者|政务移动"
)

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
                content = await self._crawl_url(url)
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
            # 去除 BM25 高亮标记（如 _互联网_ → 互联网）
            clean_title = re.sub(r"\s*_([^_]+)_\s*", r"\1", title).strip()
            # 过滤与社媒营销无关的政策文章
            if _TITLE_BLACKLIST.search(clean_title):
                continue
            result.append((clean_title, url))
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
