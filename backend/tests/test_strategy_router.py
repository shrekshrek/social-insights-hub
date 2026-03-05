"""策略路由集成测试 — Step 1 新增行为"""

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
    """创建策略时 slice_ids 可为空 — 引导路径，新行为"""
    resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "无切片策略"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "无切片策略"
    assert data["slices"] == []
    assert data["status"] == "briefing"


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
                "industry": "消费电子",
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


# ── 新增端点冒烟测试 ─────────────────────────────────────────────────────────


async def test_consult_strategy_stub_response(
    async_client: AsyncClient, auth_headers: dict
):
    """/consult 返回 ConsultResponse 并推进状态到 consulting"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "咨询测试策略"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]

    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/consult",
        json={"user_input": "我想分析竞品表现"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["round_number"] == 1
    assert "monitor_suggestions" in data
    assert "slice_plan" in data

    detail = await async_client.get(
        f"{BASE}/strategies/{strategy_id}", headers=auth_headers
    )
    assert detail.json()["status"] == "consulting"


async def test_evaluate_strategy_stub_response(
    async_client: AsyncClient, auth_headers: dict
):
    """/evaluate 返回 EvaluationResultResponse 结构"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "评估测试策略"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]

    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/evaluate",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "is_sufficient" in data
    assert "gap_analysis" in data


async def test_confirm_ready_advances_status(
    async_client: AsyncClient, auth_headers: dict
):
    """/confirm-ready 将状态推进到 slices_ready"""
    create_resp = await async_client.post(
        f"{BASE}/strategies",
        json={"name": "就绪确认测试"},
        headers=auth_headers,
    )
    strategy_id = create_resp.json()["id"]

    resp = await async_client.post(
        f"{BASE}/strategies/{strategy_id}/confirm-ready",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "slices_ready"
