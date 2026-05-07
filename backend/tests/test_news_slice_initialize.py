"""initialize_slice 集成测试 — 验证 stage1 同步落地的切片配置 + descriptive

覆盖范围：
- 0 篇文章场景：status=completed，subject/competitors 列仍写入，descriptive 是空统计
- 有文章场景：status=analyzing，descriptive 含真实统计
- 大盘视角（subject=None）：competitors 列为空数组
- 焦点视角（subject + competitors）：原样持久化到表列
- 失败任务的文章不参与（NewsTask.status=completed 过滤）

不覆盖：LLM stage2（Pass 1/2/derived）— 由 Celery 任务跑，集成测试用 mock 即可。
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import pwd_context
from src.news_media.analysis.service import initialize_slice
from src.news_media.monitors.models import NewsMonitor
from src.news_media.tasks.models import NewsArticle, NewsTask

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def slice_user(async_db_session: AsyncSession) -> User:
    user = User(
        username="slice_tester",
        email="slice_tester@test.com",
        hashed_password=pwd_context.hash("testpassword123"),
    )
    async_db_session.add(user)
    await async_db_session.flush()
    return user


@pytest_asyncio.fixture
async def news_monitor(async_db_session: AsyncSession, slice_user: User) -> NewsMonitor:
    monitor = NewsMonitor(name="测试新闻监测", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()
    return monitor


async def _make_task(
    db: AsyncSession,
    monitor: NewsMonitor,
    user: User,
    *,
    name: str,
    keywords: str,
    status: str = "completed",
) -> NewsTask:
    task = NewsTask(
        name=name,
        monitor_id=monitor.id,
        user_id=user.id,
        keywords=keywords,
        phase="collect",
        status=status,
    )
    db.add(task)
    await db.flush()
    return task


def _article(
    *,
    task_id: int,
    url: str,
    source_tier: str = "tier3",
    sentiment: float | None = 0.0,
    relevance: str = "high",
) -> NewsArticle:
    return NewsArticle(
        task_id=task_id,
        url=url,
        title=f"标题 {url}",
        source_name="测试来源",
        source_tier=source_tier,
        search_source="baidu",
        article_type="report",
        relevance=relevance,
        sentiment=sentiment,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


# ─── 场景 1：无文章 → status=completed ──────────────────────────────────────


async def test_initialize_slice_with_no_articles_marks_completed(
    async_db_session: AsyncSession,
    news_monitor: NewsMonitor,
    slice_user: User,
):
    """included tasks 没文章时，stage1 直接 completed（无需 LLM）。

    subject/competitors 列仍写入；descriptive 是空统计（articles_total=0）；stats 同步落地。
    """
    task = await _make_task(
        async_db_session, news_monitor, slice_user,
        name="空任务", keywords="kw",
    )

    slice_obj = await initialize_slice(
        async_db_session,
        monitor_id=news_monitor.id,
        name="空切片",
        included_task_ids=[task.id],
        user_id=slice_user.id,
        subject=None,
        competitors=[],
    )

    assert slice_obj.status == "completed"
    assert slice_obj.subject is None
    assert slice_obj.competitors == []
    assert slice_obj.result_data is not None
    # result_data 不含 meta 节点（已升格到表列）
    assert "meta" not in slice_obj.result_data
    assert slice_obj.result_data["descriptive"]["articles_total"] == 0
    assert slice_obj.stats is not None
    assert slice_obj.stats["articles_total"] == 0


# ─── 场景 2：有文章 → status=analyzing ──────────────────────────────────────


async def test_initialize_slice_with_articles_marks_analyzing(
    async_db_session: AsyncSession,
    news_monitor: NewsMonitor,
    slice_user: User,
):
    """有文章时 stage1 落 meta + descriptive，status=analyzing 等 Celery 跑 LLM。

    descriptive.articles_total 反映真实计数；low relevance 文章被过滤。
    """
    task = await _make_task(
        async_db_session, news_monitor, slice_user,
        name="有文章任务", keywords="kw",
    )
    async_db_session.add_all([
        _article(task_id=task.id, url="u1", source_tier="tier1", sentiment=1.0),
        _article(task_id=task.id, url="u2", source_tier="tier2", sentiment=-1.0),
        _article(task_id=task.id, url="u3", source_tier="tier3", sentiment=0.0),
        _article(task_id=task.id, url="u4", relevance="low"),  # 被过滤
    ])
    await async_db_session.flush()

    slice_obj = await initialize_slice(
        async_db_session,
        monitor_id=news_monitor.id,
        name="有数据切片",
        included_task_ids=[task.id],
        user_id=slice_user.id,
        subject=None,
        competitors=[],
    )

    assert slice_obj.status == "analyzing"
    descriptive = slice_obj.result_data["descriptive"]
    # articles_total = 跨任务 URL 命中和（含 low）；articles_filtered = 过滤后参与分析的篇数
    assert descriptive["articles_total"] == 4
    assert descriptive["articles_filtered"] == 3
    assert descriptive["source_tier_distribution"]["tier1"] == 1
    assert descriptive["source_tier_distribution"]["tier2"] == 1
    # LLM 阶段还没跑，entities/quotes/page_synthesis 不存在
    assert "entities" not in slice_obj.result_data
    assert "page_synthesis" not in slice_obj.result_data


# ─── 场景 3：焦点切片 meta 持久化 ────────────────────────────────────────────


async def test_initialize_slice_focus_persists_subject_and_competitors(
    async_db_session: AsyncSession,
    news_monitor: NewsMonitor,
    slice_user: User,
):
    """焦点切片：subject + competitors 原样写入表列（与 result_data 解耦）。"""
    task = await _make_task(
        async_db_session, news_monitor, slice_user,
        name="焦点任务", keywords="kw",
    )
    async_db_session.add(
        _article(task_id=task.id, url="u1", source_tier="tier1")
    )
    await async_db_session.flush()

    slice_obj = await initialize_slice(
        async_db_session,
        monitor_id=news_monitor.id,
        name="美赞臣蓝臻 Focus",
        included_task_ids=[task.id],
        user_id=slice_user.id,
        subject="美赞臣蓝臻",
        competitors=["惠氏启赋", "皇家美素佳儿"],
    )

    assert slice_obj.subject == "美赞臣蓝臻"
    assert slice_obj.competitors == ["惠氏启赋", "皇家美素佳儿"]
    # result_data 不含切片配置（已升格到表列）
    assert "meta" not in slice_obj.result_data


# ─── 场景 4：失败任务的文章不参与 stage1 ────────────────────────────────────


async def test_initialize_slice_skips_articles_from_failed_tasks(
    async_db_session: AsyncSession,
    news_monitor: NewsMonitor,
    slice_user: User,
):
    """initialize_slice 通过 NewsTask.status=completed 过滤——失败任务的文章不参与。"""
    completed_task = await _make_task(
        async_db_session, news_monitor, slice_user,
        name="完成任务", keywords="kw1", status="completed",
    )
    failed_task = await _make_task(
        async_db_session, news_monitor, slice_user,
        name="失败任务", keywords="kw2", status="failed",
    )
    async_db_session.add_all([
        _article(task_id=completed_task.id, url="u1"),
        _article(task_id=completed_task.id, url="u2"),
        _article(task_id=failed_task.id, url="u3"),  # 不应被计入
    ])
    await async_db_session.flush()

    slice_obj = await initialize_slice(
        async_db_session,
        monitor_id=news_monitor.id,
        name="跨任务切片",
        included_task_ids=[completed_task.id, failed_task.id],
        user_id=slice_user.id,
        subject=None,
        competitors=[],
    )

    assert slice_obj.result_data["descriptive"]["articles_total"] == 2


