"""百度新闻搜索爬虫

通过 Crawl4AI REST API 爬取百度新闻搜索结果页，返回结构化文章列表。

目标 URL：https://news.baidu.com/ns?word={query}&rn={n}&tn=news
该 URL 会 301 重定向到新版资讯搜索页
https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&word=...，
crawl4ai 会自动跟随重定向。

解析策略：
新版百度资讯页的新闻结果项在 markdown 转换后无法被识别为 markdown link
（标题/来源/时间/摘要被 markdownify 打散），因此改为从 `cleaned_html`
中用正则匹配 `#content_left` 下的 `.result-op.c-container` 块，每个块
包含一条新闻的 title/url/source_name/time/snippet。
热搜榜等右侧栏 widget 用的是不同的类名（`opr-toplist1-title`），天然被
`news-title_` 前缀过滤掉。
"""

import html as html_lib
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from src.config import settings

logger = logging.getLogger(__name__)

_BAIDU_NEWS_URL = "https://news.baidu.com/ns"

# 每个 result 块匹配：<div class="result-op c-container ..." id="N">...</div>
# 用 lookahead 切到下一个 result-op 或页脚
_RESULT_BLOCK_RE = re.compile(
    r'<div class="result-op c-container[^"]*"[^>]*id="(\d+)"[^>]*>'
    r"(.*?)"
    r'(?=<div class="result-op c-container|<div id="page"|\Z)',
    re.DOTALL,
)

# 标题 + URL：<h3 class="news-title_XXXXX"><a href="URL">TITLE</a></h3>
# news-title_ 前缀带 hash 后缀，用前缀匹配抗混淆
_TITLE_RE = re.compile(
    r'<h3[^>]*class="news-title_[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)

# 时间：<span class="c-color-gray2 ...">4小时前</span>
_TIME_RE = re.compile(r'<span class="c-color-gray2[^"]*"[^>]*>([^<]+)</span>')

# 摘要：<span class="c-font-normal c-color-text">...</span>
_SNIPPET_RE = re.compile(
    r'<span class="c-font-normal c-color-text"[^>]*>(.*?)</span>',
    re.DOTALL,
)

# 来源：news-source_XXXXX 块下的 <span class="c-color-gray">媒体名</span>
_SOURCE_RE = re.compile(
    r'<div class="news-source_[^"]*">.*?<span class="c-color-gray"[^>]*>([^<]+)</span>',
    re.DOTALL,
)


def _clean_html_text(s: str) -> str:
    """去掉 HTML 注释、内联标签（<em>等）、实体转义，返回纯文本"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).strip()


def _parse_baidu_date(date_str: str) -> datetime | None:
    """解析百度新闻返回的相对/绝对日期字符串"""
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
        m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        m = re.search(r"(\d{1,2})月(\d{1,2})日", date_str)
        if m:
            return datetime(now.year, int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc)
    except (AttributeError, ValueError):
        pass
    return None


def _extract_articles_from_html(html: str, max_results: int) -> list[dict]:
    """从 crawl4ai 的 cleaned_html 中提取百度新闻结果项

    每个 .result-op.c-container 对应一条新闻；热搜榜等非新闻 widget 没有
    news-title_ 前缀的 h3，会在提取 title 时被跳过。
    """
    articles: list[dict] = []
    seen_urls: set[str] = set()

    for _rid, block in _RESULT_BLOCK_RE.findall(html):
        if len(articles) >= max_results:
            break

        title_match = _TITLE_RE.search(block)
        if not title_match:
            continue  # 非新闻 widget（如热搜榜）

        url = title_match.group(1).replace("&amp;", "&").strip()
        title = _clean_html_text(title_match.group(2))

        if not title or len(title) < 5 or url in seen_urls:
            continue
        seen_urls.add(url)

        time_match = _TIME_RE.search(block)
        published_raw = _clean_html_text(time_match.group(1)) if time_match else ""
        published_at = _parse_baidu_date(published_raw)

        snippet_match = _SNIPPET_RE.search(block)
        snippet = _clean_html_text(snippet_match.group(1))[:300] if snippet_match else ""

        source_match = _SOURCE_RE.search(block)
        source_name = _clean_html_text(source_match.group(1)) if source_match else "未知来源"

        articles.append({
            "title": title,
            "url": url,
            "snippet": snippet or None,
            "source_name": source_name,
            "published_at": published_at,
            "image_url": None,
            "raw_data": {"title": title, "url": url, "source": source_name},
            "search_source": "baidu",
        })

    return articles


_PAGE_SIZE = 10  # 百度新闻每页实际返回约 10 条


def _fetch_one_page(session: requests.Session, url: str, headers: dict) -> str:
    """抓取单页并返回 cleaned_html，失败返回空字符串"""
    payload: dict = {
        "urls": [url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": 20000,
        },
    }
    resp = session.post(
        f"{settings.CRAWL4AI_BASE_URL}/crawl",
        json=payload,
        headers=headers,
        timeout=30.0,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return ""
    return results[0].get("cleaned_html", "")


def search_baidu_news(query: str, max_results: int = 10) -> list[dict]:
    """通过 Crawl4AI 爬取百度新闻搜索结果（自动分页，同步版）

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，每条含 title, url, snippet, source_name, published_at,
        image_url, raw_data, search_source="baidu"
    """
    encoded_query = quote(query)
    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    try:
        with requests.Session() as session:
            page = 0
            while len(all_articles) < max_results:
                pn = page * _PAGE_SIZE
                target_url = (
                    f"{_BAIDU_NEWS_URL}?word={encoded_query}"
                    f"&rn={_PAGE_SIZE}&pn={pn}&tn=news&cl=2&ie=utf-8"
                )

                cleaned_html = _fetch_one_page(session, target_url, headers)
                if not cleaned_html.strip():
                    logger.warning("百度新闻: 第 %d 页 cleaned_html 为空, query=%r", page + 1, query)
                    break

                page_articles = _extract_articles_from_html(cleaned_html, _PAGE_SIZE)
                if not page_articles:
                    break

                for a in page_articles:
                    if a["url"] not in seen_urls and len(all_articles) < max_results:
                        seen_urls.add(a["url"])
                        all_articles.append(a)

                page += 1

        logger.info("百度新闻: query=%r, 提取文章数=%d (翻页=%d)", query, len(all_articles), page)
        return all_articles

    except requests.RequestException as e:
        logger.error("Crawl4AI 请求失败: %s", e)
        raise
