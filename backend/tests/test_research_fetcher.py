"""research_agent fetch 节点测试

覆盖串行抓取的关键不变量：保序、snippet 回退、无内容丢弃、prefetched 直用，
以及软超时（SoftTimeLimitExceeded）必须向上传播（不能被 `except Exception` 吞掉，
否则任务无法在 soft_time_limit 时优雅标 failed，只能硬等强杀）。
"""

from unittest.mock import patch

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

import src.research_agent.nodes.fetcher as fetcher

_BLOCKED_PATH = "src.research_agent.nodes.filter._is_fetch_blocked"


def _candidate(url: str, **overrides) -> dict:
    base = {
        "url": url,
        "title": "标题",
        "source": "来源",
        "snippet": "兜底摘要",
        "published_date": "",
    }
    return {**base, **overrides}


def test_fetch_node_preserves_order_and_fallbacks():
    """并发抓取后仍保序；全文成功用全文，失败回退 snippet，无 snippet 则丢弃。"""
    selected = [
        _candidate("https://a.com/1"),  # HTML 抓取成功
        _candidate("https://b.com/2"),  # HTML 失败 → 回退 snippet
        _candidate("https://c.com/3", snippet=""),  # 失败且无 snippet → 丢弃
        _candidate("https://d.com/4", full_text="预取全文"),  # prefetched 直接用
    ]

    def fake_html(url: str) -> str | None:
        return "正文" * 300 if url.endswith("/1") else None

    with (
        patch.object(fetcher, "_fetch_html", side_effect=fake_html),
        patch(_BLOCKED_PATH, return_value=False),
    ):
        documents = fetcher.fetch_node(
            {"selected": selected, "profile_name": "creative"}
        )["documents"]

    # c.com 被丢弃；其余三条按 selected 原序排列
    assert [d["url"] for d in documents] == [
        "https://a.com/1",
        "https://b.com/2",
        "https://d.com/4",
    ]
    by_url = {d["url"]: d for d in documents}
    assert by_url["https://a.com/1"]["content_type"] == "html"
    assert by_url["https://b.com/2"]["content_type"] == "snippet"
    assert by_url["https://b.com/2"]["content"] == "兜底摘要"
    assert by_url["https://d.com/4"]["content"] == "预取全文"


def test_fetch_node_blocked_domain_degrades_to_snippet():
    """已知封堵域名跳过网络抓取，直接降级 snippet。"""
    selected = [_candidate("https://blocked.com/x")]
    with (
        patch.object(fetcher, "_fetch_html") as mock_html,
        patch(_BLOCKED_PATH, return_value=True),
    ):
        documents = fetcher.fetch_node(
            {"selected": selected, "profile_name": "creative"}
        )["documents"]

    mock_html.assert_not_called()
    assert documents[0]["content_type"] == "snippet"


def test_fetch_node_propagates_soft_time_limit():
    """软超时必须冒泡出 fetch_node，不能被并发 worker 的 except Exception 吞掉。"""

    def raise_soft(url: str):
        raise SoftTimeLimitExceeded()

    with (
        patch.object(fetcher, "_fetch_html", side_effect=raise_soft),
        patch(_BLOCKED_PATH, return_value=False),
        pytest.raises(SoftTimeLimitExceeded),
    ):
        fetcher.fetch_node(
            {"selected": [_candidate("https://slow.com/1")], "profile_name": "creative"}
        )


def test_fetch_node_empty_selected_returns_empty():
    """没有候选时直接返回空 documents，不触发任何抓取。"""
    assert fetcher.fetch_node({"selected": [], "profile_name": "creative"}) == {
        "documents": []
    }
