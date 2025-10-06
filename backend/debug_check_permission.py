import asyncio

import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient

from src.database import Base, get_async_db
from src.main import app
from src.redis_client import get_redis_client
from src.rbac.init_data import init_rbac_data
from src.rbac.models import SystemRoles
from src.rbac import service as rbac_service
from src.auth import service as auth_service

from tests.conftest import async_engine, AsyncTestingSessionLocal


async def main():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = AsyncTestingSessionLocal()

    async def override_get_async_db():
        try:
            yield async_session
        finally:
            pass

    test_redis = redis.from_url("redis://localhost:6379/1", decode_responses=True)

    async def override_get_redis_client():
        try:
            await test_redis.flushdb()
        except Exception:
            pass
        yield test_redis

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_redis_client] = override_get_redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await init_rbac_data(async_session)
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "admin_user", "password": "StrongPass123", "email": "admin@example.com"},
        )
        print("register", resp.status_code, resp.json())

        admin_user = await auth_service.get_user_by_username(async_session, "admin_user")
        super_role = await rbac_service.get_role_by_name(async_session, SystemRoles.SUPER_ADMIN)
        await rbac_service.assign_user_roles(async_session, admin_user.id, [super_role.id])

        login_resp = await client.post(
            "/api/v1/auth/token",
            data={"username": "admin_user", "password": "StrongPass123"},
        )
        print("login", login_resp.status_code, login_resp.json())
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        user_role = await rbac_service.get_role_by_name(async_session, SystemRoles.USER)
        print("user role id", user_role.id)
        resp = await client.post(
            "/api/v1/users",
            json={
                "username": "managed_user",
                "password": "SecurePass123",
                "email": "managed@example.com",
                "role_ids": [user_role.id],
            },
            headers=headers,
        )
        print("create", resp.status_code, resp.json())

    await async_session.close()
    await test_redis.close()


if __name__ == "__main__":
    asyncio.run(main())
