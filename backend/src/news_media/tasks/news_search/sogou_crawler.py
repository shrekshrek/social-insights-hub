"""搜狗新闻搜索爬虫

通过 Crawl4AI REST API 爬取搜狗新闻搜索结果页，返回结构化文章列表。
搜狗新闻的独特价值在于能覆盖微信公众号文章——大量行业分析、企业新闻
首发在公众号，百度搜不到。

目标 URL：https://news.sogou.com/news?query={query}&mode=1&sort=1
Crawl4AI 渲染 JS 后返回 cleaned_html。

实际 DOM 结构（2026-04 验证）：
  <div class="vrwrap" id="sogou_vr_..._wrap_N">
    <div class="news200616">
      <h3 class="vr-title">
        <a id="sogou_vr_..._N" href="/link?url=...">TITLE</a>
      </h3>
      <p class="news-from text-lightgray">
        <span>来源名</span><span>N天前</span>
      </p>
      <p class="star-wiki">摘要文本...</p>
    </div>
  </div>

注意：
- URL 是相对路径 /link?url=...，需要补全为 https://news.sogou.com/link?url=...
- 来源和时间在 news-from 的两个 <span> 子标签中，而非 \xa0 分隔的文本
"""

import html as html_lib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_SOGOU_NEWS_URL = "https://news.sogou.com/news"
_SOGOU_BASE = "https://news.sogou.com"

# ---------------------------------------------------------------------------
# 正则匹配：基于 2026-04 实际 cleaned_html 验证
# ---------------------------------------------------------------------------

# 每个结果块：<div class="vrwrap" id="sogou_vr_..._wrap_N">...</div>
# 用 lookahead 切到下一个 vrwrap 或页面尾部
_RESULT_BLOCK_RE = re.compile(
    r'<div class="vrwrap"[^>]*id="sogou_vr_[^"]*"[^>]*>'
    r"(.*?)"
    r"(?=<div class=\"vrwrap\"|<!--\s*PageFooter|<div class=\"page-nav|<div id=\"pagebar|\Z)",
    re.DOTALL,
)

# 标题 + URL：<h3 class="vr-title"><a ... href="/link?url=...">TITLE</a></h3>
_TITLE_RE = re.compile(
    r'<h3[^>]*class="vr-title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)

# 来源 + 时间：<p class="news-from ..."><span>来源</span><span>时间</span></p>
_NEWS_FROM_RE = re.compile(
    r'<p[^>]*class="[^"]*news-from[^"]*"[^>]*>(.*?)</p>',
    re.DOTALL,
)

# news-from 内部的 <span> 子标签
_SPAN_RE = re.compile(r"<span[^>]*>(.*?)</span>", re.DOTALL)

# 摘要：<p class="star-wiki">...</p>
_SNIPPET_RE = re.compile(
    r'<p[^>]*class="[^"]*star-wiki[^"]*"[^>]*>(.*?)</p>',
    re.DOTALL,
)


def _clean_html_text(s: str) -> str:
    """去掉 HTML 注释、内联标签（<em>等）、实体转义，返回纯文本"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).strip()


def _parse_sogou_date(date_str: str) -> datetime | None:
    """解析搜狗新闻返回的相对/绝对日期字符串"""
    if not date_str:
        return None
    now = datetime.now(timezone.utc)
    try:
        if "分钟前" in date_str:
            minutes = int(re.search(r"\d+", date_str).group())
            return now - timedelta(minutes=minutes)
        if "小时前" in date_str:
            hours = int(re.search(r"\d+", date_str).group())
            return now - timedelta(hours=hours)
        if "天前" in date_str:
            days = int(re.search(r"\d+", date_str).group())
            return now - timedelta(days=days)
        if "昨天" in date_str:
            return now - timedelta(days=1)
        if "前天" in date_str:
            return now - timedelta(days=2)
        # 绝对日期：2026年4月10日 或 2026-04-10
        m = re.search(r"(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})", date_str)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        # 不带年份：4月10日
        m = re.search(r"(\d{1,2})月(\d{1,2})日", date_str)
        if m:
            return datetime(now.year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        pass
    return None


def _resolve_url(raw_url: str) -> str:
    """将搜狗的相对链接 /link?url=... 转为绝对 URL"""
    raw_url = html_lib.unescape(raw_url).strip()
    if raw_url.startswith("/"):
        return f"{_SOGOU_BASE}{raw_url}"
    return raw_url


def _extract_source_time(from_html: str) -> tuple[str, str]:
    """从 news-from 块中提取来源和时间

    实际结构：<span>来源名</span><span>N天前</span>
    """
    spans = _SPAN_RE.findall(from_html)
    spans = [_clean_html_text(s) for s in spans if _clean_html_text(s)]
    if len(spans) >= 2:
        return spans[0], spans[1]
    if len(spans) == 1:
        return spans[0], ""
    # fallback: 整体文本用 \xa0 或空格拆分
    text = _clean_html_text(from_html)
    if "\xa0" in text:
        parts = text.split("\xa0")
        return parts[0].strip(), parts[-1].strip()
    return text, ""


def _extract_articles_from_html(html: str, max_results: int) -> list[dict]:
    """从 Crawl4AI 的 cleaned_html 中提取搜狗新闻结果项

    按 vrwrap 结果块逐条提取，每块内独立匹配标题/来源/时间/摘要。
    """
    articles: list[dict] = []
    seen_urls: set[str] = set()

    blocks = _RESULT_BLOCK_RE.findall(html)
    if not blocks:
        logger.warning("搜狗新闻: 未匹配到 vrwrap 结果块，cleaned_html 长度=%d", len(html))
        return []

    for block in blocks:
        if len(articles) >= max_results:
            break

        title_match = _TITLE_RE.search(block)
        if not title_match:
            continue

        raw_url = title_match.group(1)
        title = _clean_html_text(title_match.group(2))

        if not title or len(title) < 5:
            continue

        url = _resolve_url(raw_url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 来源和时间
        source_name = "未知来源"
        published_at = None
        from_match = _NEWS_FROM_RE.search(block)
        if from_match:
            source_name, time_str = _extract_source_time(from_match.group(1))
            published_at = _parse_sogou_date(time_str)

        # 摘要
        snippet = None
        snippet_match = _SNIPPET_RE.search(block)
        if snippet_match:
            snippet = _clean_html_text(snippet_match.group(1))[:300] or None

        articles.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_name": source_name or "未知来源",
            "published_at": published_at,
            "image_url": None,
            "raw_data": {"title": title, "url": url, "source": source_name},
            "search_source": "sogou",
        })

    return articles


async def search_sogou_news(query: str, max_results: int = 10) -> list[dict]:
    """通过 Crawl4AI 爬取搜狗新闻搜索结果

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，每条含 title, url, snippet, source_name, published_at,
        image_url, raw_data, search_source="sogou"
    """
    encoded_query = quote(query)
    target_url = (
        f"{_SOGOU_NEWS_URL}?query={encoded_query}"
        f"&mode=1&sort=1&ie=utf8"
    )

    payload: dict = {
        "urls": [target_url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": 25000,
            "wait_until": "networkidle",
        },
    }

    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                f"{settings.CRAWL4AI_BASE_URL}/crawl",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.warning("Crawl4AI: 搜狗新闻爬取返回空结果, query=%r", query)
            return []

        cleaned_html = results[0].get("cleaned_html", "")
        if not cleaned_html.strip():
            logger.warning("Crawl4AI: 搜狗新闻 cleaned_html 为空, query=%r", query)
            return []

        articles = _extract_articles_from_html(cleaned_html, max_results)
        logger.info("搜狗新闻: query=%r, 提取文章数=%d", query, len(articles))
        return articles

    except httpx.HTTPError as e:
        logger.error("Crawl4AI 请求失败 (搜狗): %s", e)
        raise
