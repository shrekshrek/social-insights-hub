"""news_search 模块单元测试

测试重点：
- aggregator URL 去重逻辑（含 query string 归一化）
- source_tier 分类（tier1/tier2/tier3）
- 单渠道失败降级（返回空列表，不抛异常）
- 多渠道并发合并结果
- 搜狗 HTML 解析（标题/来源/时间提取）
"""

from pathlib import Path
from unittest.mock import patch

from src.news_media.tasks.news_search.aggregator import (
    _normalize_url,
    classify_source_tier,
    search_news,
)
from src.news_media.tasks.news_search.baidu_crawler import (
    _extract_articles_from_html,
)
from src.news_media.tasks.news_search.sogou_crawler import (
    _extract_articles_from_html as _extract_sogou_articles,
    _extract_source_time,
    _parse_sogou_date,
    _resolve_url,
)
from src.news_media.tasks.news_search.wechat_mp_crawler import (
    _extract_articles_from_html as _extract_wechat_articles,
    _parse_time_convert,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ==================== classify_source_tier ====================


def test_tier1_sources():
    assert classify_source_tier("新华网") == "tier1"
    assert classify_source_tier("人民日报官方") == "tier1"
    assert classify_source_tier("澎湃新闻") == "tier1"


def test_tier2_sources():
    assert classify_source_tier("36氪") == "tier2"
    assert classify_source_tier("界面新闻") == "tier2"
    assert classify_source_tier("虎嗅网") == "tier2"


def test_tier3_fallback():
    assert classify_source_tier("百家号") == "tier3"
    assert classify_source_tier("未知来源") == "tier3"
    assert classify_source_tier("") == "tier3"


# ==================== baidu_crawler HTML parsing ====================


def _load_fixture() -> str:
    return (_FIXTURE_DIR / "baidu_news_xiaomi_su7.html").read_text(encoding="utf-8")


def test_baidu_extract_articles_from_real_html():
    """真实 cleaned_html 应提取到 >=5 条新闻，每条含核心字段"""
    html = _load_fixture()
    articles = _extract_articles_from_html(html, max_results=20)

    assert len(articles) >= 5, f"期望 >=5 条，实际 {len(articles)}"

    for a in articles:
        assert a["title"] and len(a["title"]) >= 5
        assert a["url"].startswith("http")
        assert a["source_name"] and a["source_name"] != "未知来源"
        assert a["search_source"] == "baidu"


def test_baidu_extract_skips_hot_search_widget():
    """热搜榜 widget 不应被当成新闻结果提取"""
    html = _load_fixture()
    articles = _extract_articles_from_html(html, max_results=20)

    titles = [a["title"] for a in articles]
    # 热搜榜的典型条目（这份 fixture 里确实存在）
    assert not any("外交部回应特朗普" in t for t in titles)
    assert not any("奋力谱写服务业高质量" in t for t in titles)


def test_baidu_extract_respects_max_results():
    html = _load_fixture()
    articles = _extract_articles_from_html(html, max_results=3)
    assert len(articles) == 3


def test_baidu_extract_url_dedup_within_page():
    """同一 URL 在同一页面出现多次应只保留一条"""
    html = _load_fixture()
    articles = _extract_articles_from_html(html, max_results=50)
    urls = [a["url"] for a in articles]
    assert len(urls) == len(set(urls))


def test_baidu_extract_empty_html():
    assert _extract_articles_from_html("", max_results=10) == []
    assert _extract_articles_from_html("<html><body></body></html>", max_results=10) == []


def test_baidu_extracted_sources_classify_non_tier3():
    """提取的来源中至少部分能被 _SOURCE_TIERS 分到 tier2（证明字典不虚设）"""
    html = _load_fixture()
    articles = _extract_articles_from_html(html, max_results=20)
    tiers = {classify_source_tier(a["source_name"]) for a in articles}
    assert "tier2" in tiers, f"期望至少一条 tier2，实际 tiers={tiers}"


# ==================== _normalize_url ====================


def test_normalize_url_strips_tracking_params():
    url = "https://example.com/news/article-123?utm_source=baidu&from=news"
    assert _normalize_url(url) == "https://example.com/news/article-123"


def test_normalize_url_keeps_identity_params():
    """baijiahao id 参数是文章唯一标识，不能去掉"""
    url = "https://baijiahao.baidu.com/s?id=123456&wfr=spider&for=pc"
    normalized = _normalize_url(url)
    assert "id=123456" in normalized
    assert "wfr" not in normalized


def test_normalize_url_keeps_sogou_url_param():
    """搜狗 /link?url=xxx 的 url 参数是文章标识"""
    url = "https://news.sogou.com/link?url=abcdef123"
    normalized = _normalize_url(url)
    assert "url=abcdef123" in normalized


def test_normalize_url_keeps_path():
    url = "https://xinhuanet.com/2026/04/05/news.html"
    assert _normalize_url(url) == "https://xinhuanet.com/2026/04/05/news.html"


def test_normalize_url_strips_trailing_slash():
    url = "https://example.com/news/"
    assert _normalize_url(url) == "https://example.com/news"


def test_normalize_url_handles_no_query():
    url = "https://example.com/article/123"
    assert _normalize_url(url) == "https://example.com/article/123"


# ==================== search_news (aggregator) ====================


def test_search_news_deduplicates_same_url():
    """同一 URL 来自两个渠道，只保留一条"""
    shared_url = "https://example.com/news/shared-article"
    baidu_result = [{
        "title": "共同文章", "url": shared_url, "snippet": "...",
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    sogou_result = [{
        "title": "共同文章", "url": shared_url, "snippet": "...",
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "sogou",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result),
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", return_value=sogou_result),
    ):
        results = search_news("测试", channels=["baidu", "sogou"])

    assert len(results) == 1
    assert results[0]["url"] == shared_url


def test_search_news_merges_unique_articles():
    """两个渠道各有独立文章，合并后全部保留"""
    baidu_result = [{
        "title": "百度独有", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    sogou_result = [{
        "title": "搜狗独有", "url": "https://bloomberg.com/a2", "snippet": None,
        "source_name": "Bloomberg", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "sogou",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result),
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", return_value=sogou_result),
    ):
        results = search_news("测试", channels=["baidu", "sogou"])

    assert len(results) == 2
    urls = {r["url"] for r in results}
    assert "https://xinhua.com/a1" in urls
    assert "https://bloomberg.com/a2" in urls


def test_search_news_adds_source_tier():
    """聚合后每条文章都有 source_tier 字段"""
    baidu_result = [{
        "title": "新华社报道", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华社", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result):
        results = search_news("测试", channels=["baidu"])

    assert results[0]["source_tier"] == "tier1"


def test_search_news_baidu_only_channel():
    """channels=["baidu"] 时不调用搜狗"""
    baidu_result = [{
        "title": "百度结果", "url": "https://example.com/a1", "snippet": None,
        "source_name": "人民网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result) as mock_baidu,
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news") as mock_sogou,
    ):
        results = search_news("测试", channels=["baidu"])

    mock_baidu.assert_called_once()
    mock_sogou.assert_not_called()
    assert len(results) == 1


def test_search_news_url_dedup_with_tracking_params():
    """同一文章不同追踪参数的 URL 视为重复"""
    baidu_result = [{
        "title": "文章A", "url": "https://example.com/news?id=1&from=baidu",
        "snippet": None, "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    sogou_result = [{
        "title": "文章A", "url": "https://example.com/news?id=1&utm_source=sogou",
        "snippet": None, "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "sogou",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result),
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", return_value=sogou_result),
    ):
        results = search_news("测试", channels=["baidu", "sogou"])

    # 追踪参数去掉后 id=1 相同，应去重
    assert len(results) == 1


# ==================== sogou_crawler ====================


def test_sogou_parse_date_relative():
    """搜狗相对时间解析"""
    assert _parse_sogou_date("3小时前") is not None
    assert _parse_sogou_date("30分钟前") is not None
    assert _parse_sogou_date("2天前") is not None


def test_sogou_parse_date_absolute():
    """搜狗绝对日期解析"""
    dt = _parse_sogou_date("2026年4月10日")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 4 and dt.day == 10

    dt2 = _parse_sogou_date("2026-04-10")
    assert dt2 is not None and dt2.year == 2026


def test_sogou_parse_date_none():
    assert _parse_sogou_date("") is None
    assert _parse_sogou_date(None) is None


def test_sogou_resolve_url_relative():
    """相对路径 /link?url=... 应补全为绝对 URL"""
    url = _resolve_url("/link?url=abcdef123")
    assert url == "https://news.sogou.com/link?url=abcdef123"


def test_sogou_resolve_url_absolute():
    """绝对 URL 应原样返回"""
    url = _resolve_url("https://example.com/news")
    assert url == "https://example.com/news"


def test_sogou_extract_source_time_spans():
    """news-from 中 <span>来源</span><span>时间</span> 结构"""
    source, time = _extract_source_time('<span>澎湃新闻</span><span>2小时前</span>')
    assert source == "澎湃新闻"
    assert time == "2小时前"


def test_sogou_extract_source_time_nbsp_fallback():
    """news-from 中无 span 时回退到 \\xa0 分隔"""
    source, time = _extract_source_time("新华网\xa03天前")
    assert source == "新华网"
    assert time == "3天前"


def test_sogou_extract_source_time_single_span():
    source, time = _extract_source_time('<span>某来源</span>')
    assert source == "某来源"
    assert time == ""


_SOGOU_FIXTURE_HTML = """
<div class="vrwrap" id="sogou_vr_30010280_wrap_1">
    <div class="news200616">
        <h3 class="vr-title">
            <a id="sogou_vr_30010280_1" href="/link?url=abc123">
                深度解读新一代<em>小米SU7</em>
            </a>
        </h3>
        <p class="news-from text-lightgray">
            <span>汽车之家</span><span>1天前</span>
        </p>
        <p class="star-wiki">
            新一代小米SU7彻底告别初代400V平台,实现高压架构突破...
        </p>
    </div>
</div>
<div class="vrwrap" id="sogou_vr_30010280_wrap_2">
    <div class="news200616">
        <h3 class="vr-title">
            <a id="sogou_vr_30010280_2" href="/link?url=def456">
                新能源汽车市场分析报告正式发布
            </a>
        </h3>
        <p class="news-from text-lightgray">
            <span>第一财经</span><span>3小时前</span>
        </p>
        <p class="star-wiki">
            最新市场报告显示新能源汽车渗透率持续攀升...
        </p>
    </div>
</div>
"""


def test_sogou_extract_vrwrap_pattern():
    """搜狗 vrwrap 结果块应正确提取标题/来源/时间/摘要"""
    articles = _extract_sogou_articles(_SOGOU_FIXTURE_HTML, max_results=10)
    assert len(articles) == 2

    a1 = articles[0]
    assert a1["title"] == "深度解读新一代小米SU7"
    assert a1["url"] == "https://news.sogou.com/link?url=abc123"
    assert a1["source_name"] == "汽车之家"
    assert a1["published_at"] is not None
    assert a1["snippet"] is not None
    assert "400V" in a1["snippet"]
    assert a1["search_source"] == "sogou"

    a2 = articles[1]
    assert a2["source_name"] == "第一财经"


def test_sogou_extract_empty_html():
    assert _extract_sogou_articles("", max_results=10) == []
    assert _extract_sogou_articles("<html><body></body></html>", max_results=10) == []


def test_sogou_extract_respects_max_results():
    articles = _extract_sogou_articles(_SOGOU_FIXTURE_HTML, max_results=1)
    assert len(articles) == 1


def test_sogou_extract_dedup_within_page():
    """同一 URL 只保留一条"""
    html = """
    <div class="vrwrap" id="sogou_vr_1_wrap_1">
        <h3 class="vr-title"><a href="/link?url=same">重复新闻的标题内容一</a></h3>
    </div>
    <div class="vrwrap" id="sogou_vr_1_wrap_2">
        <h3 class="vr-title"><a href="/link?url=same">重复新闻的标题内容二</a></h3>
    </div>
    """
    articles = _extract_sogou_articles(html, max_results=10)
    assert len(articles) == 1


def test_sogou_extract_filters_short_titles():
    """标题过短（<5字符）的条目应被过滤"""
    html = """
    <div class="vrwrap" id="sogou_vr_1_wrap_1">
        <h3 class="vr-title"><a href="/link?url=a1">短标题</a></h3>
    </div>
    <div class="vrwrap" id="sogou_vr_1_wrap_2">
        <h3 class="vr-title"><a href="/link?url=b2">这是一个足够长的新闻标题</a></h3>
    </div>
    """
    articles = _extract_sogou_articles(html, max_results=10)
    assert len(articles) == 1
    assert articles[0]["title"] == "这是一个足够长的新闻标题"


# ==================== wechat_mp_crawler ====================


def test_wechat_parse_time_from_rendered_span():
    """crawl4ai cleaned_html 剥掉 <script> 后，日期落在 <span class="s2">YYYY-M-D</span>"""
    block = '<div class="s-p"><span class="all-time-y2">某公众号</span><span class="s2">2026-1-30</span></div>'
    dt = _parse_time_convert(block)
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2026, 1, 30)


def test_wechat_parse_time_falls_back_to_timeconvert_script():
    """rendered span 缺失时，降级到 timeConvert('unix_ts')"""
    block = "<script>document.write(timeConvert('1735689600'))</script>"  # 2025-01-01 UTC
    dt = _parse_time_convert(block)
    assert dt is not None
    assert dt.year == 2025 and dt.month == 1 and dt.day == 1


def test_wechat_parse_time_returns_none_when_missing():
    assert _parse_time_convert("<div>no date here</div>") is None


def test_wechat_extract_li_with_attrs():
    """搜狗微信结果项是 <li id="sogou_vr_..."> 带属性，必须能匹配"""
    html = """
    <ul class="news-list">
      <li id="sogou_vr_11002601_box_0">
        <h3><a href="/link?url=abc123">公众号文章标题足够长</a></h3>
        <p class="txt-info">这是摘要内容</p>
        <div class="s-p">
          <span class="all-time-y2">独立出海联合体</span>
          <span class="s2">2026-1-30</span>
        </div>
      </li>
    </ul>
    """
    articles = _extract_wechat_articles(html, max_results=10)
    assert len(articles) == 1
    a = articles[0]
    assert a["title"] == "公众号文章标题足够长"
    assert a["source_name"] == "独立出海联合体"
    assert a["url"].endswith("/link?url=abc123")
    assert a["published_at"] is not None
    assert a["search_source"] == "wechat_mp"


# ==================== aggregator: 三渠道 ====================


def test_search_news_sogou_channel():
    """channels=["sogou"] 时只调用搜狗"""
    sogou_result = [{
        "title": "搜狗结果", "url": "https://example.com/sg1", "snippet": None,
        "source_name": "澎湃新闻", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "sogou",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news") as mock_baidu,
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", return_value=sogou_result) as mock_sogou,
    ):
        results = search_news("测试", channels=["sogou"])

    mock_baidu.assert_not_called()
    mock_sogou.assert_called_once()
    assert len(results) == 1
    assert results[0]["search_source"] == "sogou"


def test_search_news_sogou_failure_degrades_gracefully():
    """搜狗失败时不影响百度结果"""
    baidu_result = [{
        "title": "百度结果", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result),
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", side_effect=Exception("Sogou error")),
    ):
        results = search_news("测试", channels=["baidu", "sogou"])

    assert len(results) == 1
    assert results[0]["source_name"] == "新华网"


def test_search_news_three_channels_merge():
    """三渠道（baidu + sogou + wechat_mp）结果合并去重"""
    baidu_result = [{
        "title": "百度独有", "url": "https://xinhua.com/a1", "snippet": None,
        "source_name": "新华网", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "baidu",
    }]
    sogou_result = [{
        "title": "搜狗独有", "url": "https://thepaper.cn/a2", "snippet": None,
        "source_name": "澎湃新闻", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "sogou",
    }]
    wechat_result = [{
        "title": "公众号独有", "url": "https://mp.weixin.qq.com/a3", "snippet": None,
        "source_name": "某公众号", "published_at": None,
        "image_url": None, "raw_data": {}, "search_source": "wechat_mp",
    }]

    with (
        patch("src.news_media.tasks.news_search.baidu_crawler.search_baidu_news", return_value=baidu_result),
        patch("src.news_media.tasks.news_search.sogou_crawler.search_sogou_news", return_value=sogou_result),
        patch("src.news_media.tasks.news_search.wechat_mp_crawler.search_wechat_mp", return_value=wechat_result),
    ):
        results = search_news("测试", channels=["baidu", "sogou", "wechat_mp"])

    assert len(results) == 3
    sources = {r["search_source"] for r in results}
    assert sources == {"baidu", "sogou", "wechat_mp"}
