"""Convenience helpers for invoking signature strategies."""

from __future__ import annotations

from typing import Any, Dict

from .factory import get_signature_strategy
from .schemas import SignatureRequest


class SignatureGenerationError(RuntimeError):
    """Raised when signature generation fails."""


async def generate_signature(
    platform: str, payload: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    strategy = get_signature_strategy()
    request = SignatureRequest(platform=platform, payload=payload or {})
    response = await strategy.generate(request)
    if not response.success or not response.data:
        raise SignatureGenerationError(response.message or "签名生成失败")
    return response.data
