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

_INDEX_URL = "https://www.cnnic.cn/hlwfzyj/hlwxzbg/"
_PDF_PATTERN = re.compile(r"https?://[^\s\"']+\.pdf", re.IGNORECASE)
_REPORT_KEYWORD = "hlwxzbg"  # 互联网络发展状况统计报告 URL 特征


class CNNICCrawler(BaseCrawler):
    """CNNIC 互联网发展统计报告爬取器"""

    source_type = "cnnic"

    async def discover(self) -> list[CrawlSource]:
        logger.info("[cnnic] 抓取报告列表页: %s", _INDEX_URL)
        markdown = await self._crawl_url(_INDEX_URL, query="互联网发展统计报告")

        pdf_urls = self._extract_pdf_urls(markdown)
        logger.info("[cnnic] 发现 %d 个 PDF 链接", len(pdf_urls))

        sources = []
        for url in pdf_urls:
            try:
                pdf_bytes = await self._download_pdf(url)
                title = self._title_from_url(url)
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

    def _extract_pdf_urls(self, markdown: str) -> list[str]:
        """从 Markdown 中提取 CNNIC 报告 PDF 链接"""
        urls = _PDF_PATTERN.findall(markdown)
        seen: set[str] = set()
        result = []
        for url in urls:
            url = url.rstrip(")")  # Markdown 链接可能携带尾部括号
            if _REPORT_KEYWORD in url and url not in seen:
                seen.add(url)
                result.append(url)
        return result

    async def _download_pdf(self, url: str) -> bytes:
        """用 httpx 直接下载 PDF 字节"""
        async with httpx.AsyncClient(
            timeout=settings_timeout(),
            follow_redirects=True,
            verify=False,  # 部分政府站点自签证书
            headers={"User-Agent": "Mozilla/5.0 (compatible; SIH-Crawler/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    def _title_from_url(self, url: str) -> str:
        """从 URL 推断报告标题"""
        filename = url.rsplit("/", 1)[-1].replace(".pdf", "")
        year = self._year_from_url(url)
        if year:
            return f"CNNIC 第{self._issue_from_url(url)}次互联网络发展状况统计报告（{year}年）"
        return f"CNNIC 互联网络发展状况统计报告 {filename}"

    def _year_from_url(self, url: str) -> int | None:
        m = re.search(r"(20\d{2})", url)
        return int(m.group(1)) if m else None

    def _issue_from_url(self, url: str) -> str:
        """尝试从 URL 推断期次（如第54次）"""
        m = re.search(r"(\d{2,3})ci|hlwxzbg(\d{2,3})", url, re.IGNORECASE)
        if m:
            return m.group(1) or m.group(2)
        return "N"


def settings_timeout() -> float:
    from src.config import settings
    return float(settings.CRAWLER_PDF_TIMEOUT)
