"""搜狗微信公众号搜索爬虫

通过 Crawl4AI REST API 爬取搜狗微信搜索结果页，返回结构化公众号文章列表。
与 sogou_crawler.py（搜狗新闻搜索）互补：本模块搜索的是纯微信公众号文章，
覆盖品牌号、行业号、自媒体等在微信封闭生态内首发的内容。

目标 URL：https://weixin.sogou.com/weixin?type=2&query={query}&ie=utf8
type=2 表示搜文章（type=1 是搜公众号主页）。

实际 DOM 结构（参考爬虫端 extractor 验证）：
  <ul class="news-list">
    <li>
      <h3><a href="/link?url=...">TITLE</a></h3>
      <p class="txt-info">摘要文本...</p>
      <div class="s-p">
        <span class="all-time-y2">公众号名称</span>
        <script>document.write(timeConvert('unix_ts'))</script>
      </div>
    </li>
  </ul>

注意：
- 搜索结果链接是搜狗跳转 URL（/link?url=...），Crawl4AI 全文抓取时会自动跟随跳转到 mp.weixin.qq.com
- 公众号名称在 all-time-y2 class 的 span 中
- 发布时间藏在 timeConvert('unix_ts') 的 JS 脚本中
"""

import html as html_lib
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from src.config import settings
from src.news_media.tasks.news_search._crawl4ai_client import fetch_via_crawl4ai

logger = logging.getLogger(__name__)

_WEIXIN_SOGOU_URL = "https://weixin.sogou.com/weixin"
_SOGOU_BASE = "https://weixin.sogou.com"

# ---------------------------------------------------------------------------
# 正则匹配：基于搜狗微信搜索结果页 DOM
# ---------------------------------------------------------------------------

# 每个结果项：<li ...> inside <ul class="news-list">
# 实际 DOM 是 `<li id="sogou_vr_11002601_box_0">` 这种带属性的形式，
# 早先版本写死 `<li>` 导致长期 0 提取（搜狗没改结构，是正则一直没对上）。
_LIST_ITEM_RE = re.compile(
    r"<li[^>]*>(.*?)</li>",
    re.DOTALL,
)

# 标题 + URL：<h3><a href="...">TITLE</a></h3>
_TITLE_RE = re.compile(
    r"<h3[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
    re.DOTALL,
)

# 摘要：<p class="txt-info">...</p>
_DIGEST_RE = re.compile(
    r'<p[^>]*class="[^"]*txt-info[^"]*"[^>]*>(.*?)</p>',
    re.DOTALL,
)

# 公众号名称：<span class="all-time-y2">...</span> 或 <a ...>name</a> 在 s-p 区域
_ACCOUNT_RE = re.compile(
    r'<span[^>]*class="[^"]*all-time-y2[^"]*"[^>]*>(.*?)</span>',
    re.DOTALL,
)

# 发布时间有两种形式：
#   1) crawl4ai 跑过 JS → 渲染结果直接写进 <span class="s2">2026-1-30</span>（首选）
#   2) 原始 timeConvert('unix_ts') 脚本（cleaned_html 一般会被剥掉 <script>，几乎匹配不到，留作降级）
_RENDERED_DATE_RE = re.compile(r'<span[^>]*class="[^"]*\bs2\b[^"]*"[^>]*>([^<]+)</span>')
_TIME_CONVERT_RE = re.compile(r"timeConvert\(['\"](\d+)['\"]\)")


def _clean_html_text(s: str) -> str:
    """去掉 HTML 注释、内联标签（<em>等）、实体转义，返回纯文本"""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).strip()


def _parse_time_convert(html_block: str) -> datetime | None:
    """优先从渲染后的 <span class="s2"> 文本里取日期（如 "2026-1-30"），
    再降级到 timeConvert('unix_ts') 脚本。crawl4ai cleaned_html 会剥 <script>，
    脚本路径几乎走不到，但保留以防 crawl4ai 配置变化。"""
    # 路径 1：渲染后的字面日期（cleaned_html 实际场景）
    rendered = _RENDERED_DATE_RE.search(html_block)
    if rendered:
        date_str = rendered.group(1).strip()
        # 形如 2026-1-30 / 2026-01-30 / 2026/1/30
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except ValueError:
                pass

    # 路径 2：原始 timeConvert 脚本（降级）
    match = _TIME_CONVERT_RE.search(html_block)
    if match:
        try:
            ts = int(match.group(1))
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    return None


def _resolve_url(raw_url: str) -> str:
    """将搜狗的相对链接 /link?url=... 转为绝对 URL"""
    raw_url = html_lib.unescape(raw_url).strip()
    if raw_url.startswith("/"):
        return f"{_SOGOU_BASE}{raw_url}"
    return raw_url


def _extract_articles_from_html(html: str, max_results: int) -> list[dict]:
    """从 Crawl4AI 的 cleaned_html 中提取搜狗微信搜索结果

    逐个 <li> 提取标题/链接/摘要/公众号名/发布时间。
    """
    # 先定位 news-list 区域
    news_list_match = re.search(
        r'<ul[^>]*class="[^"]*news-list[^"]*"[^>]*>(.*?)</ul>',
        html,
        re.DOTALL,
    )
    if not news_list_match:
        logger.warning("搜狗微信: 未匹配到 news-list，cleaned_html 长度=%d", len(html))
        return []

    list_html = news_list_match.group(1)
    items = _LIST_ITEM_RE.findall(list_html)
    if not items:
        logger.warning("搜狗微信: news-list 中未匹配到 <li> 项")
        return []

    articles: list[dict] = []
    seen_urls: set[str] = set()

    for item_html in items:
        if len(articles) >= max_results:
            break

        title_match = _TITLE_RE.search(item_html)
        if not title_match:
            continue

        raw_url = title_match.group(1)
        title = _clean_html_text(title_match.group(2))

        if not title or len(title) < 3:
            continue

        url = _resolve_url(raw_url)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # 摘要
        snippet = None
        digest_match = _DIGEST_RE.search(item_html)
        if digest_match:
            snippet = _clean_html_text(digest_match.group(1))[:300] or None

        # 公众号名称
        source_name = "未知公众号"
        account_match = _ACCOUNT_RE.search(item_html)
        if account_match:
            name = _clean_html_text(account_match.group(1))
            if name:
                source_name = name

        # 发布时间
        published_at = _parse_time_convert(item_html)

        articles.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "source_name": source_name,
            "published_at": published_at,
            "image_url": None,
            "raw_data": {"title": title, "url": url, "source": source_name},
            "search_source": "wechat_mp",
        })

    return articles


_PAGE_SIZE = 10  # 搜狗微信每页约 10 条
_MAX_PAGES = 5  # 最多翻 5 页（50 条）兜底——防止结果耗尽后的重复页导致无限翻页


def _fetch_one_page(session: requests.Session, url: str, headers: dict) -> str:
    """抓取单页并返回 cleaned_html，失败返回空字符串

    通过共享的 fetch_via_crawl4ai helper 访问 crawl4ai，自动对 5xx + 网络错误做
    指数退避重试，抹平搜狗微信入口反爬的瞬时抖动。
    """
    result = fetch_via_crawl4ai(
        session, url, headers,
        page_timeout=30000,
        wait_until="networkidle",
        http_timeout=40.0,
    )
    if not result:
        return ""
    return result.get("cleaned_html", "")


def search_wechat_mp(query: str, max_results: int = 10) -> list[dict]:
    """通过 Crawl4AI 爬取搜狗微信公众号搜索结果（自动分页，同步版）

    Args:
        query: 搜索关键词
        max_results: 最大结果数

    Returns:
        结构化文章列表，每条含 title, url, snippet, source_name, published_at,
        image_url, raw_data, search_source="wechat_mp"
    """
    encoded_query = quote(query)
    headers: dict[str, str] = {}
    if settings.CRAWL4AI_TOKEN:
        headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    try:
        with requests.Session() as session:
            page = 1
            while len(all_articles) < max_results and page <= _MAX_PAGES:
                target_url = (
                    f"{_WEIXIN_SOGOU_URL}?type=2&query={encoded_query}"
                    f"&ie=utf8&_sug_type_=&s_from=input&_sug_=n&page={page}"
                )

                cleaned_html = _fetch_one_page(session, target_url, headers)
                if not cleaned_html.strip():
                    logger.warning("搜狗微信: 第 %d 页 cleaned_html 为空, query=%r", page, query)
                    break

                page_articles = _extract_articles_from_html(cleaned_html, _PAGE_SIZE)
                if not page_articles:
                    break

                added_this_page = 0
                for a in page_articles:
                    if a["url"] not in seen_urls and len(all_articles) < max_results:
                        seen_urls.add(a["url"])
                        all_articles.append(a)
                        added_this_page += 1

                if added_this_page == 0:
                    logger.info(
                        "搜狗微信: 第 %d 页无新增 URL（%d 条全为重复），判定结果已耗尽, query=%r",
                        page, len(page_articles), query,
                    )
                    break

                page += 1

        logger.info("搜狗微信: query=%r, 提取文章数=%d (翻页=%d)", query, len(all_articles), page - 1)
        return all_articles

    except requests.RequestException as e:
        logger.error("Crawl4AI 请求失败 (搜狗微信): %s", e)
        raise
