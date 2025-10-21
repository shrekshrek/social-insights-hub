import pytest

from src.signing.schemas import SignatureRequest
from src.signing.strategies.playwright import (
    PlaywrightSignatureStrategy,
    _PLAYWRIGHT_AVAILABLE,
)


@pytest.mark.asyncio
async def test_playwright_strategy_rejects_unknown_platform():
    strategy = PlaywrightSignatureStrategy()
    request = SignatureRequest(platform="douyin", payload={})
    response = await strategy.generate(request)
    assert response.success is False
    assert "Unsupported platform" in (response.message or "")


@pytest.mark.asyncio
async def test_playwright_strategy_handles_unavailable_runtime():
    strategy = PlaywrightSignatureStrategy()
    if _PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright is available, runtime failure not expected")

    request = SignatureRequest(platform="xhs", payload={})
    response = await strategy.generate(request)
    assert response.success is False
    assert "Playwright runtime is not available" in (response.message or "")
