import random

import pytest
import redis.asyncio as redis
from httpx import AsyncClient

from src.auth import service as auth_service

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_payload():
    return {
        "email": f"test_{int(random.random() * 10000)}@example.com",
        "username": f"testuser_{int(random.random() * 10000)}",
        "password": "testpassword123",
    }


async def _register_payload(redis_client: redis.Redis, user_payload: dict) -> dict:
    """注册已改邀请制（UserCreate 必填 invite_token，email 由邀请决定）。

    测试侧直接用 service 造 token（等价于管理员触发邀请邮件后的链接），
    请求体不再携带 email。
    """
    token = await auth_service.create_invite_token(
        redis_client, email=user_payload["email"]
    )
    return {
        "username": user_payload["username"],
        "password": user_payload["password"],
        "invite_token": token,
    }


async def test_register_user_successfully(
    async_client: AsyncClient, redis_client: redis.Redis, user_payload: dict
):
    """
    Test user registration endpoint (invite-based).
    """
    payload = await _register_payload(redis_client, user_payload)
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    # email 来自邀请 token payload，不来自请求体
    assert data["email"] == user_payload["email"]
    assert data["username"] == user_payload["username"]
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_existing_user_fails(
    async_client: AsyncClient, redis_client: redis.Redis, user_payload: dict
):
    """
    Test that registering a user with an existing username/email fails.
    """
    # First registration should succeed
    payload1 = await _register_payload(redis_client, user_payload)
    response1 = await async_client.post("/api/v1/auth/register", json=payload1)
    assert response1.status_code == 201

    # Second registration: token 一次性消费，需新 token（同 username/email）
    payload2 = await _register_payload(redis_client, user_payload)
    response2 = await async_client.post("/api/v1/auth/register", json=payload2)
    assert response2.status_code == 409  # Conflict status code for duplicate resource
    assert "already exists" in response2.json()["error"]["message"]


async def test_register_with_invalid_invite_token_fails(
    async_client: AsyncClient, user_payload: dict
):
    """无效/过期邀请 token → 400"""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "username": user_payload["username"],
            "password": user_payload["password"],
            "invite_token": "nonexistent-token",
        },
    )
    assert response.status_code == 400


async def test_full_auth_flow(
    async_client: AsyncClient, redis_client: redis.Redis, user_payload: dict
):
    """
    Test the full authentication flow: register -> login -> get me -> logout -> fail get me.
    """
    # 1. Register (invite-based)
    payload = await _register_payload(redis_client, user_payload)
    register_response = await async_client.post("/api/v1/auth/register", json=payload)
    assert register_response.status_code == 201
    user_data = register_response.json()

    # 2. Login
    login_payload = {
        "username": user_payload["username"],
        "password": user_payload["password"],
    }
    login_response = await async_client.post("/api/v1/auth/token", data=login_payload)
    assert login_response.status_code == 200
    token_data = login_response.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Get Me (Protected Route)
    me_response = await async_client.get("/api/v1/users/me", headers=headers)
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["id"] == user_data["id"]
    assert me_data["email"] == user_payload["email"]

    # 4. Logout
    logout_response = await async_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 200
    assert "Successfully logged out" in logout_response.json()["message"]

    # 5. Fail to Get Me (Token is blacklisted)
    fail_me_response = await async_client.get("/api/v1/users/me", headers=headers)
    assert fail_me_response.status_code == 401
    assert "Token has been revoked" in fail_me_response.json()["detail"]
