"""新闻搜索多渠道聚合器（同步版）

并发调用百度新闻、搜狗新闻、Bing 新闻（均通过 Crawl4AI）和可选微信公众号，
按 URL 去重合并，返回统一结构的文章列表（含 source_tier 分类）。

使用 gevent.pool 做多渠道并发（gevent monkey-patch 下底层 socket 自动协作让出）。
本模块由 Celery gevent worker 调用，全路径无 asyncio。
"""

import logging
from urllib.parse import parse_qs, urlparse, urlencode

from gevent.pool import Pool

logger = logging.getLogger(__name__)

# 中国新闻来源权威度分层
_SOURCE_TIERS: dict[str, list[str]] = {
    "tier1": [
        "新华网", "新华社", "人民日报", "人民网", "央视", "央视网", "CCTV",
        "中国日报", "经济日报", "光明日报", "环球时报", "中国新闻网", "澎湃新闻",
        "新华每日电讯", "参考消息", "半月谈",
    ],
    "tier2": [
        "第一财经", "财新", "财新网", "21世纪经济报道", "每日经济新闻",
        "界面新闻", "36氪", "虎嗅", "新浪财经", "新浪科技", "腾讯新闻", "腾讯科技",
        "网易新闻", "网易科技", "搜狐新闻", "凤凰网", "凤凰财经",
        "南方都市报", "南方周末", "北京青年报", "新京报", "证券时报",
        "中国证券报", "上海证券报", "经济观察报", "IT之家", "钛媒体",
        # 省级党报 / 地方主流（采样命中）
        "上观新闻", "解放日报", "新民晚报", "文汇报",
        "极目新闻", "湖北日报", "楚天都市报",
        "海报新闻", "大众日报", "齐鲁晚报",
        "红星新闻", "成都商报", "封面新闻",
        "潇湘晨报", "扬子晚报", "现代快报",
    ],
}


def classify_source_tier(source_name: str) -> str:
    """根据来源名称判断权威度分层"""
    for tier, sources in _SOURCE_TIERS.items():
        if any(name in source_name for name in sources):
            return tier
    return "tier3"


# 这些 query 参数是文章的唯一标识符，去重时必须保留
_IDENTITY_PARAMS: set[str] = {"id", "url", "docid", "nid", "aid", "artid", "newsid"}

# 常见追踪参数，去重时应剥离
_TRACKING_PARAMS: set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "from", "wfr", "for", "spider", "isappinstalled", "scene", "clicktime",
    "enterid", "spm", "share_token", "tt_from", "channel",
}


def _normalize_url(url: str) -> str:
    """URL 归一化，去除追踪参数但保留文章标识参数，用于去重

    baijiahao.baidu.com/s?id=xxx 和 news.sogou.com/link?url=xxx 中的
    id/url 参数是文章唯一标识，不能去掉。
    """
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url.rstrip("/")
        params = parse_qs(parsed.query, keep_blank_values=False)
        # 只保留身份参数和非追踪参数
        filtered = {
            k: v for k, v in params.items()
            if k.lower() in _IDENTITY_PARAMS or k.lower() not in _TRACKING_PARAMS
        }
        if not filtered:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        # 排序保证同参数不同顺序的 URL 归一化结果一致
        sorted_qs = urlencode(filtered, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{sorted_qs}".rstrip("/")
    except Exception:
        return url


def search_news(
    query: str,
    max_results: int = 50,
    channels: list[str] | None = None,
    raw_counts_out: dict[str, int] | None = None,
) -> list[dict]:
    """多渠道并发搜索，URL 去重合并，附加 source_tier（同步版）

    Args:
        query: 搜索关键词
        max_results: 每个渠道的最大结果数
        channels: 启用的渠道列表，默认 ["baidu", "sogou", "bing"]
        raw_counts_out: 可选的输出字典。若提供，填充**去重前**每渠道的原始召回量，
            形如 `{"baidu": 15, "sogou": 20, "bing": 8, "wechat_mp": 3}`。
            用于让调用方了解各渠道的真实 yield（区别于"入库数量 = 去重后"）。

    Returns:
        去重后的文章列表，每条含标准字段 + source_tier + search_source
    """
    if channels is None:
        channels = ["baidu", "sogou", "bing"]

    # 构造 (fn, args) 列表，用 gevent.pool 并发执行
    jobs: list = []
    if "baidu" in channels:
        from src.news_media.tasks.news_search.baidu_crawler import search_baidu_news
        jobs.append((search_baidu_news, (query,), {"max_results": max_results}))
    if "sogou" in channels:
        from src.news_media.tasks.news_search.sogou_crawler import search_sogou_news
        jobs.append((search_sogou_news, (query,), {"max_results": max_results}))
    if "bing" in channels:
        from src.news_media.tasks.news_search.bing_crawler import search_bing_news
        jobs.append((search_bing_news, (query,), {"max_results": max_results}))
    if "wechat_mp" in channels:
        from src.news_media.tasks.news_search.wechat_mp_crawler import search_wechat_mp
        jobs.append((search_wechat_mp, (query,), {"max_results": max_results}))

    if not jobs:
        return []

    def _safe_call(job: tuple) -> list[dict] | Exception:
        fn, args, kwargs = job
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return e

    # gevent.pool 并发执行，单渠道失败不影响其他渠道
    # 并发度 = len(jobs)，单任务内渠道数量有限（<=4）
    pool = Pool(len(jobs))
    raw_results = list(pool.imap_unordered(_safe_call, jobs))

    # 同时统计每渠道**去重前**的原始召回量（用于评估渠道 yield 健康度）
    raw_counts: dict[str, int] = {}
    all_articles: list[dict] = []
    for result in raw_results:
        if isinstance(result, Exception):
            logger.warning("搜索渠道异常（已忽略）: %s", result)
            continue
        for article in result:
            src = article.get("search_source", "unknown")
            raw_counts[src] = raw_counts.get(src, 0) + 1
        all_articles.extend(result)

    # URL 归一化去重（保留先出现的）
    seen_normalized: set[str] = set()
    deduped: list[dict] = []
    for article in all_articles:
        norm = _normalize_url(article["url"])
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)

        # 补充 source_tier（公众号文章使用独立分层标识）
        if article.get("search_source") == "wechat_mp":
            article["source_tier"] = "wechat_mp"
        else:
            article["source_tier"] = classify_source_tier(article.get("source_name", ""))
        deduped.append(article)

    logger.info(
        "聚合搜索: query=%r, channels=%s, 原始=%d, 去重后=%d, per_channel_raw=%s",
        query, channels, len(all_articles), len(deduped), raw_counts,
    )

    if raw_counts_out is not None:
        raw_counts_out.update(raw_counts)

    return deduped
