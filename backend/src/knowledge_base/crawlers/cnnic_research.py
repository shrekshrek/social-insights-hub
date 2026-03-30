"""CNNIC 专题研究报告爬取

策略：
1. Crawl4AI 抓取报告列表页，提取文章链接（/n4/.../c88-*.html）
2. 逐篇文章页提取 PDF 下载链接（/NMediaFile/...）
3. httpx 下载 PDF，走现有 parse_text + chunk + embed 管线
"""

import logging
import re

import httpx

from .base import BaseCrawler, CrawlSource

logger = logging.getLogger(__name__)

_LIST_URL = "https://www.cnnic.net.cn/6/86/88/index.html"
_BASE_URL = "https://www.cnnic.net.cn"

# 文章路径模式：/n4/{year}/{date}/c88-{id}.html（HTML 中为相对路径）
_ARTICLE_PATTERN = re.compile(r'(/n4/\d{4}/\d{4}/c88-\d+\.html)')

# 文章页内 PDF 链接：/NMediaFile/...
_PDF_PATTERN = re.compile(r'href="(/NMediaFile/[^"]+\.pdf)"', re.IGNORECASE)

# 文章标题：《...》
_TITLE_PATTERN = re.compile(r'[《「\u201c]([^》」\u201d]+)[》」\u201d]')


class CNNICResearchCrawler(BaseCrawler):
    """CNNIC 专题研究报告爬取器（AI、数字消费、中小企业等）"""

    source_type = "cnnic_research"

    async def discover(self) -> list[CrawlSource]:
        logger.info("[cnnic_research] 抓取报告列表: %s", _LIST_URL)
        html = await self._fetch_html(_LIST_URL)

        article_urls = self._extract_article_urls(html)
        logger.info("[cnnic_research] 发现 %d 篇研究报告文章", len(article_urls))

        sources = []
        for article_url in article_urls:
            try:
                pdf_url, title = await self._extract_pdf_from_article(article_url)
                if not pdf_url:
                    logger.info("[cnnic_research] 无 PDF 下载链接，跳过: %s", article_url)
                    continue
                full_pdf_url = _BASE_URL + pdf_url
                pdf_bytes = await self._download_pdf(full_pdf_url)
                sources.append(
                    CrawlSource(
                        url=article_url,
                        title=title,
                        file_bytes=pdf_bytes,
                        filename=pdf_url.rsplit("/", 1)[-1],
                        source_meta={"source": "cnnic_research"},
                    )
                )
                logger.info("[cnnic_research] 已下载: %s", title)
            except Exception as e:
                logger.warning("[cnnic_research] 跳过 %s: %s", article_url, e)

        return sources

    async def _fetch_html(self, url: str) -> str:
        """直接用 httpx 获取 HTML（政府站点服务端渲染，无需 Playwright）"""
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    def _extract_article_urls(self, html: str) -> list[str]:
        """从列表页 HTML 提取文章链接（去重）"""
        seen: set[str] = set()
        result = []
        for m in _ARTICLE_PATTERN.finditer(html):
            path = m.group(1)
            url = _BASE_URL + path
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    async def _extract_pdf_from_article(self, url: str) -> tuple[str | None, str]:
        """抓取文章页，提取 PDF 链接和标题"""
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SIH-Crawler/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        pdf_match = _PDF_PATTERN.search(html)
        pdf_path = pdf_match.group(1) if pdf_match else None

        title_match = re.search(r"<title>(.*?)(?:--[^<]*)?\s*</title>", html)
        raw_title = title_match.group(1).strip() if title_match else ""
        m = _TITLE_PATTERN.search(raw_title)
        title = m.group(1) if m else raw_title or url.rsplit("/", 1)[-1]

        return pdf_path, title

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
