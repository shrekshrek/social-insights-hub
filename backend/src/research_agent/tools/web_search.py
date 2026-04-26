"""Tavily 定向搜索工具

同步调用（gevent 兼容），始终使用 include_domains 定向搜索。
只搜索指定权威域名，不做开放全网搜索。
支持双 API Key：主 key 额度耗尽时自动切换备用 key；两个 key 都耗尽时抛
`TavilyQuotaExhaustedError`，由 Celery 任务入口捕获后把任务标为 failed +
明确的 error_message 提示用户（属于运维事件，不做优雅降级）。
"""

import logging

from tavily import TavilyClient
from tavily.errors import ForbiddenError, UsageLimitExceededError

from src.config import get_settings

logger = logging.getLogger(__name__)


class TavilyQuotaExhaustedError(Exception):
    """所有 Tavily API key 的配额都已耗尽。

    用户可见错误：由 tasks.py 捕获后写入 ResearchTask.error_message，
    前端任务详情页会直接显示。
    """


# Tavily SDK 用两种异常表达"额度耗尽"，都需要触发切换到下一个 key：
#   - UsageLimitExceededError: 免费配额触顶
#   - ForbiddenError: paid/dev key 触达 dashboard 配置的自定义 usage limit
#     （实测信息："This request exceeds this API key's set usage limit."）
_QUOTA_EXHAUSTED_EXCEPTIONS = (UsageLimitExceededError, ForbiddenError)


def _get_api_keys() -> list[str]:
    """返回可用的 Tavily API key 列表（主 key 在前）"""
    settings = get_settings()
    keys: list[str] = []
    if settings.TAVILY_API_KEY:
        keys.append(settings.TAVILY_API_KEY)
    if settings.TAVILY_API_KEY_2:
        keys.append(settings.TAVILY_API_KEY_2)
    return keys


def tavily_search(
    query: str,
    target_domains: list[str],
    max_results: int = 10,
) -> list[dict]:
    """Tavily 定向搜索，返回候选列表

    Parameters
    ----------
    query : 搜索关键词
    target_domains : include_domains 定向搜索域名（必须）
    max_results : 最大结果数

    Returns
    -------
    list[dict] : [{title, url, snippet, score}]

    Raises
    ------
    TavilyQuotaExhaustedError : 两个 API key 都配额耗尽时抛出
    """
    api_keys = _get_api_keys()
    if not api_keys:
        logger.warning("TAVILY_API_KEY 未配置，跳过搜索")
        return []

    if not target_domains:
        logger.warning("target_domains 为空，跳过搜索")
        return []

    for i, key in enumerate(api_keys):
        client = TavilyClient(api_key=key)
        try:
            resp = client.search(
                query=query,
                include_domains=target_domains,
                max_results=max_results,
                search_depth="advanced",
            )
            results = resp.get("results", [])

            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ]
        except _QUOTA_EXHAUSTED_EXCEPTIONS as e:
            key_label = "主" if i == 0 else "备用"
            if i + 1 < len(api_keys):
                logger.warning(
                    "Tavily %s key 额度耗尽（%s），切换到下一个 key: query=%s",
                    key_label,
                    type(e).__name__,
                    query,
                )
                continue
            logger.error("Tavily 所有 key 额度均已耗尽: query=%s", query)
            raise TavilyQuotaExhaustedError(
                "Tavily 搜索配额已耗尽（主 key 与备用 key 均不可用）。"
                "请联系管理员充值或等待下月配额刷新。"
            ) from None
        except Exception:
            logger.exception("Tavily 搜索失败: query=%s", query)
            return []

    return []
