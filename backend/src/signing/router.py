"""FastAPI router exposing signing service health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from .factory import get_signature_strategy
from .schemas import SignatureHealth

router = APIRouter(prefix="/signing", tags=["Signing"])


@router.get("/health", response_model=SignatureHealth, summary="签名服务健康检查")
async def signing_health_check() -> SignatureHealth:
    strategy = get_signature_strategy()
    return await strategy.health_check()
