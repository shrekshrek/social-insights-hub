import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.resources import service as resource_service
from src.resources.models import CrawlerAccount, CrawlerProxy
from src.resources.schemas import (
    CrawlerAccountCreate,
    CrawlerAccountUpdate,
    CrawlerProxyCreate,
    CrawlerProxyUpdate,
)
from src.tasks.models import CrawlerTask, PlatformType, CrawlerType, TaskStatus

pytestmark = pytest.mark.asyncio


async def _create_task(db: AsyncSession) -> CrawlerTask:
    task = CrawlerTask(
        name="test",
        platform=PlatformType.XHS,
        crawler_type=CrawlerType.SEARCH,
        status=TaskStatus.PENDING,
        config={},
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def test_allocate_and_release_account(async_db_session: AsyncSession):
    account = await resource_service.create_account(
        async_db_session,
        CrawlerAccountCreate(
            platform=PlatformType.XHS, account_name="acc1", cookies="cookie"
        ),
    )

    updated = await resource_service.update_account(
        async_db_session,
        account.id,
        CrawlerAccountUpdate(account_name="acc2", is_active=False),
    )
    assert updated is not None
    assert updated.account_name == "acc2"
    assert updated.is_active is False

    task = await _create_task(async_db_session)

    allocated = await resource_service.allocate_account(
        async_db_session, PlatformType.XHS, task.id
    )
    assert allocated is not None
    assert allocated.id == account.id
    assert allocated.locked_by_task_id == task.id

    await resource_service.release_account(
        async_db_session, allocated.id, success=False
    )
    refreshed = await async_db_session.get(CrawlerAccount, allocated.id)
    assert refreshed.locked_by_task_id is None
    assert refreshed.failure_count == 1


async def test_allocate_proxy(async_db_session: AsyncSession):
    proxy = await resource_service.create_proxy(
        async_db_session,
        CrawlerProxyCreate(host="127.0.0.1", port=8080),
    )

    updated = await resource_service.update_proxy(
        async_db_session,
        proxy.id,
        CrawlerProxyUpdate(label="test-proxy", is_active=False),
    )
    assert updated is not None
    assert updated.label == "test-proxy"
    assert updated.is_active is False

    task = await _create_task(async_db_session)

    allocated = await resource_service.allocate_proxy(async_db_session, task.id)
    assert allocated is not None
    assert allocated.id == proxy.id

    await resource_service.release_proxy(async_db_session, allocated.id, success=True)
    refreshed = await async_db_session.get(CrawlerProxy, allocated.id)
    assert refreshed.locked_by_task_id is None
    assert refreshed.failure_count == 0
