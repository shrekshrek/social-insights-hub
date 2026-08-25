"""SocialSlice / NewsSlice subject + competitors 列契约测试

保证两边切片表的 subject (str|None) 和 competitors (list[str]) 列：
- 能正常写入和读出
- 默认值符合预期（competitors 默认 []）
- 配置（列）与分析产物（result_data）解耦：写 result_data 不影响 subject 列

对 News 已有 test_news_slice_initialize.py 覆盖端到端的 stage1 路径；本文件仅做
最小契约检查，重点是社媒侧：full create_monitor_slice 端到端测试需要 Platform/
SocialPost/PostAnalysis/RBAC 完整 fixture，此处不展开。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import pwd_context
from src.news_media.analysis.models import NewsSlice
from src.news_media.monitors.models import NewsMonitor
from src.social_media.analysis.models import SocialSlice
from src.social_media.monitors.models import SocialMonitor

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def slice_user(async_db_session: AsyncSession) -> User:
    user = User(
        username="slice_columns_user",
        email="slice_columns_user@test.com",
        hashed_password=pwd_context.hash("testpassword123"),
    )
    async_db_session.add(user)
    await async_db_session.flush()
    return user


# ─── SocialSlice 列契约 ─────────────────────────────────────────────────


async def test_social_slice_persists_subject_and_competitors_columns(
    async_db_session: AsyncSession,
    slice_user: User,
):
    """SocialSlice 焦点切片：subject + competitors 落到表列，可读出。"""
    monitor = SocialMonitor(name="测试社媒监测", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()

    s = SocialSlice(
        name="星澜 Focus",
        monitor_id=monitor.id,
        user_id=slice_user.id,
        included_task_ids=[1, 2],
        subject="星澜至臻",
        competitors=["晨贝儿天赋", "皇家优诺佳"],
        result_data={"foundation": {}},
        status="completed",
    )
    async_db_session.add(s)
    await async_db_session.commit()
    await async_db_session.refresh(s)

    assert s.subject == "星澜至臻"
    assert s.competitors == ["晨贝儿天赋", "皇家优诺佳"]
    # 配置不在 result_data
    assert "meta" not in (s.result_data or {}) or "subject" not in (
        (s.result_data or {}).get("meta") or {}
    )


async def test_social_slice_landscape_mode_defaults(
    async_db_session: AsyncSession,
    slice_user: User,
):
    """SocialSlice 大盘切片：subject=None / competitors=[] 默认正确。"""
    monitor = SocialMonitor(name="测试社媒监测2", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()

    s = SocialSlice(
        name="大盘",
        monitor_id=monitor.id,
        user_id=slice_user.id,
        included_task_ids=[1],
        subject=None,
        competitors=[],
        result_data={},
        status="pending",
    )
    async_db_session.add(s)
    await async_db_session.commit()
    await async_db_session.refresh(s)

    assert s.subject is None
    assert s.competitors == []


async def test_social_slice_default_competitors_empty_list(
    async_db_session: AsyncSession,
    slice_user: User,
):
    """SocialSlice competitors 列默认值 = [] (server_default '[]'::json)。"""
    monitor = SocialMonitor(name="测试社媒监测3", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()

    # 不显式传 competitors
    s = SocialSlice(
        name="默认值测试",
        monitor_id=monitor.id,
        user_id=slice_user.id,
        included_task_ids=[1],
        result_data={},
        status="pending",
    )
    async_db_session.add(s)
    await async_db_session.commit()
    await async_db_session.refresh(s)

    assert s.competitors == []


async def test_social_slice_result_data_overwrite_preserves_columns(
    async_db_session: AsyncSession,
    slice_user: User,
):
    """关键防御点：LLM 重跑覆写 result_data 不会清掉 subject/competitors。"""
    monitor = SocialMonitor(name="测试社媒监测4", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()

    s = SocialSlice(
        name="持久性测试",
        monitor_id=monitor.id,
        user_id=slice_user.id,
        included_task_ids=[1],
        subject="某品牌",
        competitors=["竞品A", "竞品B"],
        result_data={"old": "stage1"},
        status="analyzing",
    )
    async_db_session.add(s)
    await async_db_session.commit()
    await async_db_session.refresh(s)

    # 模拟 LLM 重跑：完全覆写 result_data
    s.result_data = {"foundation": {}, "layers": {}, "reports": {}}
    s.status = "completed"
    await async_db_session.commit()
    await async_db_session.refresh(s)

    # 配置必须保留
    assert s.subject == "某品牌"
    assert s.competitors == ["竞品A", "竞品B"]


# ─── NewsSlice 列契约 ─────────────────────────────────────────────────


async def test_news_slice_result_data_overwrite_preserves_columns(
    async_db_session: AsyncSession,
    slice_user: User,
):
    """NewsSlice：Celery 重跑 merge result_data 不清 subject/competitors。"""
    monitor = NewsMonitor(name="测试新闻监测", user_id=slice_user.id)
    async_db_session.add(monitor)
    await async_db_session.flush()

    n = NewsSlice(
        name="新闻焦点",
        monitor_id=monitor.id,
        user_id=slice_user.id,
        included_task_ids=[10],
        subject="测试主体",
        competitors=["竞品X"],
        result_data={"descriptive": {"articles_total": 0}},
        status="analyzing",
    )
    async_db_session.add(n)
    await async_db_session.commit()
    await async_db_session.refresh(n)

    # 模拟 Celery 完整 merge 后的 result_data
    n.result_data = {
        "descriptive": {"articles_total": 50},
        "entities": [],
        "page_synthesis": {"briefing": {}},
    }
    n.status = "completed"
    await async_db_session.commit()
    await async_db_session.refresh(n)

    assert n.subject == "测试主体"
    assert n.competitors == ["竞品X"]
