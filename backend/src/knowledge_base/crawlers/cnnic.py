"""CNNIC 互联网发展统计报告爬取

策略：
1. Crawl4AI 抓取报告列表页，提取 PDF 链接
2. httpx 直接下载 PDF 字节（PDF 不需要浏览器）
3. 封装为 CrawlSource，走现有 parse_text + chunk + embed 管线
"""

import logging
import re

import httpx

from .base import BaseCrawler, CrawlSource

logger = logging.getLogger(__name__)

_INDEX_URL = "https://www.cnnic.com.cn/IDR/ReportDownloads/"

# Markdown 链接：[The 55th Survey Report](https://...pdf)
_LINK_PATTERN = re.compile(
    r"\[([^\]]+Survey Report[^\]]*)\]\((https://www\.cnnic\.com\.cn[^\)]+\.pdf)\)",
    re.IGNORECASE,
)

# 英文序数 → 数字：55th → 55
_ORDINAL_PATTERN = re.compile(r"(\d+)(?:st|nd|rd|th)", re.IGNORECASE)


class CNNICCrawler(BaseCrawler):
    """CNNIC 互联网络发展状况统计报告爬取器"""

    source_type = "cnnic"

    async def discover(self) -> list[CrawlSource]:
        logger.info("[cnnic] 抓取报告列表页: %s", _INDEX_URL)
        markdown = await self._crawl_url(_INDEX_URL, query="互联网发展统计报告")

        entries = self._extract_entries(markdown)
        logger.info("[cnnic] 发现 %d 份报告", len(entries))

        sources = []
        for title, url in entries:
            try:
                pdf_bytes = await self._download_pdf(url)
                year = self._year_from_url(url)
                sources.append(
                    CrawlSource(
                        url=url,
                        title=title,
                        file_bytes=pdf_bytes,
                        filename=url.rsplit("/", 1)[-1],
                        source_meta={"year": year, "source": "cnnic"},
                    )
                )
                logger.info("[cnnic] 已下载: %s", title)
            except Exception as e:
                logger.warning("[cnnic] 跳过 %s: %s", url, e)

        return sources

    def _extract_entries(self, markdown: str) -> list[tuple[str, str]]:
        """从列表页 Markdown 提取（中文标题, PDF URL）对，去重"""
        seen: set[str] = set()
        result = []
        for m in _LINK_PATTERN.finditer(markdown):
            link_text, url = m.group(1).strip(), m.group(2)
            if url in seen:
                continue
            seen.add(url)
            title = self._localize_title(link_text, url)
            result.append((title, url))
        return result

    def _localize_title(self, link_text: str, url: str) -> str:
        """将 'The 55th Survey Report' 转为中文标题"""
        m = _ORDINAL_PATTERN.search(link_text)
        issue = m.group(1) if m else "?"
        year = self._year_from_url(url)
        year_str = f"（{year}年）" if year else ""
        return f"CNNIC 第{issue}次互联网络发展状况统计报告{year_str}"

    def _year_from_url(self, url: str) -> int | None:
        m = re.search(r"/(20\d{2})\d{2}/", url)
        return int(m.group(1)) if m else None

    async def _download_pdf(self, url: str) -> bytes:
        async with httpx.AsyncClient(
            timeout=settings_timeout(),
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SIH-Crawler/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content


def settings_timeout() -> float:
    from src.config import settings
    return float(settings.CRAWLER_PDF_TIMEOUT)
