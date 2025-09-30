import pytest
import random
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_payload():
    return {
        "email": f"test_{int(random.random() * 10000)}@example.com",
        "username": f"testuser_{int(random.random() * 10000)}",
        "password": "testpassword123",
    }


async def test_register_user_successfully(
    async_client: AsyncClient, user_payload: dict
):
    """
    Test user registration endpoint.
    """
    response = await async_client.post("/api/v1/auth/register", json=user_payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_payload["email"]
    assert data["username"] == user_payload["username"]
    assert "id" in data
    assert "hashed_password" not in data


async def test_register_existing_user_fails(
    async_client: AsyncClient, user_payload: dict
):
    """
    Test that registering a user with an existing email/username fails.
    """
    # First registration should succeed
    response1 = await async_client.post("/api/v1/auth/register", json=user_payload)
    assert response1.status_code == 201

    # Second registration should fail
    response2 = await async_client.post("/api/v1/auth/register", json=user_payload)
    assert response2.status_code == 409  # Conflict status code for duplicate resource
    assert "already exists" in response2.json()["error"]["message"]


async def test_full_auth_flow(async_client: AsyncClient, user_payload: dict):
    """
    Test the full authentication flow: register -> login -> get me -> logout -> fail get me.
    """
    # 1. Register
    register_response = await async_client.post(
        "/api/v1/auth/register", json=user_payload
    )
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
    assert "Successfully logged out" in logout_response.json()["msg"]

    # 5. Fail to Get Me (Token is blacklisted)
    fail_me_response = await async_client.get("/api/v1/users/me", headers=headers)
    assert fail_me_response.status_code == 401
    assert "Token has been revoked" in fail_me_response.json()["detail"]
