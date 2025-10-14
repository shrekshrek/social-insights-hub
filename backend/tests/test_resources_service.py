import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.resources import service as resource_service
from src.resources.models import CrawlerAccount
from src.resources.schemas import (
    CrawlerAccountCreate,
    CrawlerAccountUpdate,
    ProxyProviderCreate,
    ProxyProviderUpdate,
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


async def test_proxy_provider_flow(async_db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    provider = await resource_service.create_proxy_provider(
        async_db_session,
        ProxyProviderCreate(
            name="默认快代理",
            secret_id="sid",
            signature="sig",
            username="user",
            password="pwd",
            pool_size=5,
        ),
    )

    updated = await resource_service.update_proxy_provider(
        async_db_session, provider.id, ProxyProviderUpdate(is_active=True, pool_size=3)
    )
    assert updated is not None
    assert updated.pool_size == 3

    async def fake_fetch(_provider, count):
        return [
            resource_service.ProxyEndpoint(
                host="127.0.0.1",
                port=8000 + index,
                protocol="http",
                username="user",
                password="pwd",
                expires_in=60,
            )
            for index in range(count)
        ]

    async def fake_acquire():
        return None

    monkeypatch.setattr(resource_service, "_fetch_proxies_from_kdl", fake_fetch)
    monkeypatch.setattr(resource_service, "_acquire_redis_client", fake_acquire)

    status = await resource_service.refresh_proxy_pool(async_db_session, provider.id)
    assert status.provider_id == provider.id
    assert status.available == 3

    allocation = await resource_service.allocate_proxy_endpoint(async_db_session, provider.id)
    assert allocation is not None
    assert allocation.host == "127.0.0.1"

    pool_status = await resource_service.get_proxy_pool_status(async_db_session, provider.id)
    assert pool_status is not None
    assert pool_status.provider_id == provider.id
