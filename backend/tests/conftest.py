import asyncio
import os
from typing import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
import redis.asyncio as redis
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.database import Base, get_async_db
from src.main import app
from src.rbac.init_data import init_rbac_data

# 加载测试环境变量
env_path = Path(__file__).parent.parent / ".env.test"
load_dotenv(dotenv_path=env_path, override=True)

# --- Database Fixtures ---
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db"
)

# 使用 NullPool 避免连接池问题
async_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,  # 测试时不使用连接池
    echo=False,  # 设置为 True 可以看到 SQL 语句
)

AsyncTestingSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def setup_database():
    """创建所有表结构（会话级别，只执行一次）"""
    async with async_engine.begin() as conn:
        # 删除所有表并重新创建
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncTestingSessionLocal() as seed_session:
        await init_rbac_data(seed_session)
        await seed_session.commit()
    yield
    # 测试结束后清理
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """
    提供事务性的异步数据库会话
    每个测试在独立的事务中运行，测试结束后自动回滚
    """
    async with async_engine.connect() as connection:
        # 开始事务
        transaction = await connection.begin()

        # 创建会话并绑定到事务
        async_session = AsyncTestingSessionLocal(bind=connection)

        # 嵌套事务支持（用于测试中的 commit）
        await connection.begin_nested()

        @event.listens_for(async_session.sync_session, "after_transaction_end")
        def restart_savepoint(session, transaction):
            if connection.closed:
                return
            if not connection.in_nested_transaction():
                connection.sync_connection.begin_nested()

        yield async_session

        # 回滚事务，清理测试数据
        await async_session.close()
        await transaction.rollback()


# --- Application and Client Fixtures ---
@pytest_asyncio.fixture
async def async_client(
    async_db_session: AsyncSession,
    redis_client: redis.Redis,
) -> AsyncGenerator[AsyncClient, None]:
    """提供 FastAPI 应用的异步测试客户端"""
    from src.redis_client import get_redis_client

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_db_session

    async def override_get_redis_client() -> AsyncGenerator[redis.Redis, None]:
        yield redis_client

    # 覆盖数据库和Redis依赖
    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_redis_client] = override_get_redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as client:
        yield client

    # 清理依赖覆盖
    app.dependency_overrides.clear()


# --- Redis Fixture ---
@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """提供测试用的 Redis 客户端"""
    # 使用测试专用的 Redis 数据库（编号 1）
    test_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
    client = redis.from_url(test_redis_url, decode_responses=True)

    # 清理测试数据库
    await client.flushdb()
    yield client
    # 测试后再次清理
    await client.flushdb()
    await client.close()


# --- 实用 Fixtures ---
@pytest.fixture
def anyio_backend():
    """指定 anyio 的后端为 asyncio"""
    return "asyncio"
