"""Crawl4AI HTTP 客户端（带重试 + 退避）

所有新闻渠道爬虫（baidu / sogou / wechat_mp）共享此 helper 与 crawl4ai 服务通信。
bing_crawler.py 保留作备用但不接入聚合器，也复用本 helper。
失败模式共享：target 站反爬 → crawl4ai 返回 5xx；网络层 connect/timeout。
抹平瞬时抖动，避免因为单次偶发就让该渠道本轮贡献 0 条。

重试策略：
- 默认 2 次重试（总计尝试 3 次），指数退避 5s → 15s
- 只对 5xx 服务端错误 + 网络错误（Connect/Timeout）重试；4xx 为请求错误重试无益，直接抛
- 最终仍失败则抛原异常，由 aggregator 的 _safe_call 捕获并记 warning
"""

import logging
import time

import requests

from src.config import settings

logger = logging.getLogger(__name__)

# 重试次数与退避秒数（数组长度需 >= max_retries）
_DEFAULT_RETRY_DELAYS: tuple[float, ...] = (5.0, 15.0)


def fetch_via_crawl4ai(
    session: requests.Session,
    url: str,
    headers: dict,
    *,
    page_timeout: int = 20000,
    wait_until: str | None = None,
    http_timeout: float = 30.0,
    max_retries: int = 2,
    retry_delays: tuple[float, ...] = _DEFAULT_RETRY_DELAYS,
) -> dict | None:
    """通过 crawl4ai 抓取一个页面，返回第一个 result 字典（含 cleaned_html / markdown / links 等）

    调用方按需从 result 里取 cleaned_html（百度/搜狗/微信）或 markdown（Bing 爬虫，备用）。

    Args:
        session: 调用方复用的 requests.Session
        url: 目标 URL（target 站的页面）
        headers: 传给 crawl4ai 的 headers（用于 CRAWL4AI_TOKEN 认证）
        page_timeout: crawl4ai 内部浏览器加载超时（毫秒）
        wait_until: 浏览器等待条件（None / "domcontentloaded" / "networkidle"）
        http_timeout: requests 层 HTTP 超时（秒）
        max_retries: 最多重试次数（0 = 不重试）
        retry_delays: 每次重试前等待秒数，支持指数退避配置

    Returns:
        result 字典，或 None（crawl4ai 返回空 results 数组）。
        重试耗尽后仍失败则抛最后一次异常（通常是 requests.HTTPError / ConnectionError）。
    """
    payload: dict = {
        "urls": [url],
        "crawler_config": {
            "cache_mode": "bypass",
            "scan_full_page": True,
            "page_timeout": page_timeout,
        },
    }
    if wait_until is not None:
        payload["crawler_config"]["wait_until"] = wait_until

    for attempt in range(max_retries + 1):  # 0 = 第一次，1..max_retries 为重试
        try:
            resp = session.post(
                f"{settings.CRAWL4AI_BASE_URL}/crawl",
                json=payload,
                headers=headers,
                timeout=http_timeout,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None
            return results[0]

        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            # 4xx 是请求问题，重试无意义；5xx 和无 status 才重试
            if status < 500 or attempt >= max_retries:
                raise
            delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
            logger.warning(
                "Crawl4AI %d, 重试 %d/%d，%.1fs 后重试: url=%s",
                status, attempt + 1, max_retries, delay, url,
            )
            time.sleep(delay)

        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt >= max_retries:
                raise
            delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
            logger.warning(
                "Crawl4AI %s, 重试 %d/%d，%.1fs 后重试: url=%s",
                type(e).__name__, attempt + 1, max_retries, delay, url,
            )
            time.sleep(delay)

    # 理论上不会到这里（最后一次迭代要么 return 要么 raise）
    return None
