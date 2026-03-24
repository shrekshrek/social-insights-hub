"""策略路由集成测试 — Strategy Research Engine 端点"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token, pwd_context

pytestmark = pytest.mark.asyncio

BASE = "/api/v1"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def strategy_user(async_db_session: AsyncSession) -> tuple[User, str]:
    """直接创建测试用户（绕过 API 速率限制），返回 (user, token)"""
    user = User(
        username="strategy_tester",
        email="strategy_tester@test.com",
        hashed_password=pwd_context.hash("testpassword123"),
    )
    async_db_session.add(user)
    await async_db_session.flush()
    token = create_access_token(user.username)
    return user, token


@pytest_asyncio.fixture
async def auth_headers(strategy_user: tuple[User, str]) -> dict:
    _, token = strategy_user
    return {"Authorization": f"Bearer {token}"}


# ── Create Strategy ─────────────────────────────────────────────────────────


async def test_create_strategy_without_slice_ids(
    async_client: AsyncClient, auth_headers: dict
):
    """创建策略时 slice_ids 可为空 — 默认 status=draft"""
    resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "无切片策略"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "无切片策略"
    assert data["slices"] == []
    assert data["status"] == "draft"


async def test_create_strategy_with_brand_brief(
    async_client: AsyncClient, auth_headers: dict
):
    """创建策略时附带结构化 BrandBrief"""
    resp = await async_client.post(
        f"{BASE}/strategies",
        json={
            "name": "有 Brief 策略",
            "brand_brief": {
                "brand_name": "测试品牌",
                "analysis_goal": "提升品牌认知",
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["brand_brief"]["brand_name"] == "测试品牌"
    assert data["brand_brief"]["analysis_goal"] == "提升品牌认知"


# ── Phase 1 前置检查 ─────────────────────────────────────────────────────────


async def test_generate_phase1_without_slices_returns_400(
    async_client: AsyncClient, auth_headers: dict
):
    """Phase 1 生成时若无切片关联 → 400 Bad Request"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "无切片 Phase1 测试"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    strategy_id = create_resp.json()["id"]

    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/generate/phase1",
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "切片" in resp.json()["detail"]


# ── 旧端点已移除确认 ─────────────────────────────────────────────────────────


async def test_old_consult_endpoint_removed(
    async_client: AsyncClient, auth_headers: dict
):
    """/consult 端点已被 /design-research 替代 → 405 或 404"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "旧端点测试"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]
    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/consult",
        json={"user_input": "test"},
        headers=auth_headers,
    )
    assert resp.status_code in (404, 405)


async def test_old_evaluate_endpoint_removed(
    async_client: AsyncClient, auth_headers: dict
):
    """/evaluate 端点已移除 → 405 或 404"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "旧端点测试2"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]
    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/evaluate",
        headers=auth_headers,
    )
    assert resp.status_code in (404, 405)


async def test_old_confirm_ready_endpoint_removed(
    async_client: AsyncClient, auth_headers: dict
):
    """/confirm-ready 端点已移除 → 405 或 404"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "旧端点测试3"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]
    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/confirm-ready",
        headers=auth_headers,
    )
    assert resp.status_code in (404, 405)
