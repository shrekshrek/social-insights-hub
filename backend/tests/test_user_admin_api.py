import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_service
from src.rbac import service as rbac_service
from src.rbac.models import SystemRoles


pytestmark = pytest.mark.asyncio


async def _prepare_super_admin(
    db: AsyncSession,
    async_client: AsyncClient,
    username: str,
    password: str,
    email: str,
) -> dict:
    """创建并登录超级管理员，返回认证头信息"""

    register_payload = {
        "username": username,
        "password": password,
        "email": email,
    }
    response = await async_client.post("/api/v1/auth/register", json=register_payload)
    assert response.status_code == 201

    admin_user = await auth_service.get_user_by_username(db, username)
    assert admin_user is not None

    super_role = await rbac_service.get_role_by_name(db, SystemRoles.SUPER_ADMIN)
    assert super_role is not None

    await rbac_service.assign_user_roles(db, admin_user.id, [super_role.id])

    login_payload = {"username": username, "password": password}
    login_response = await async_client.post("/api/v1/auth/token", data=login_payload)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_admin_can_create_user_with_roles(
    async_client: AsyncClient,
    async_db_session: AsyncSession,
):
    headers = await _prepare_super_admin(
        async_db_session,
        async_client,
        username="admin_user",
        password="StrongPass123",
        email="admin@example.com",
    )

    user_role = await rbac_service.get_role_by_name(async_db_session, SystemRoles.USER)
    assert user_role is not None

    create_payload = {
        "username": "managed_user",
        "password": "SecurePass123",
        "email": "managed@example.com",
        "role_ids": [user_role.id],
    }

    response = await async_client.post(
        "/api/v1/users", json=create_payload, headers=headers
    )

    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "managed_user"
    assert "user" in data.get("roles", [])

    managed_user = await auth_service.get_user_by_username(
        async_db_session, "managed_user"
    )
    assert managed_user is not None

    managed_roles = await rbac_service.get_user_roles(async_db_session, managed_user.id)
    role_names = {role.name for role in managed_roles}
    assert SystemRoles.USER in role_names
