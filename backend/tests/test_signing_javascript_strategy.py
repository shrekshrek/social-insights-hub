import pytest

from src.signing.schemas import SignatureRequest
from src.signing.strategies.javascript import JavascriptSignatureStrategy


@pytest.mark.asyncio
async def test_javascript_strategy_fallback_when_payload_missing():
    strategy = JavascriptSignatureStrategy()
    request = SignatureRequest(platform="xhs", payload={"keyword": "ai"})
    response = await strategy.generate(request)

    assert response.success is True
    assert "signature" in response.data
    assert "timestamp" in response.data


@pytest.mark.asyncio
async def test_javascript_strategy_xhs_real_signature():
    strategy = JavascriptSignatureStrategy()
    available = strategy.is_platform_available("xhs")
    print("is_platform_available", available)
    if not available:
        pytest.skip("XHS javascript signer unavailable in this environment")

    request = SignatureRequest(
        platform="xhs",
        payload={
            "uri": "/api/sns/web/v1/homefeed",
            "data": {"cursor_score": "", "num": 10, "refresh_type": 1},
            "cookies": "a1=191394056e84h1l1gj7lon307ihadu15e3xp1vaaa30000526867",
        },
    )
    response = await strategy.generate(request)

    assert response.success is True
    data = response.data or {}
    assert "x-s" in data and isinstance(data["x-s"], str)
    assert "x-t" in data and isinstance(data["x-t"], str)
    assert "x-mns" in data and isinstance(data["x-mns"], str)
