"""FastAPI router exposing signing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, status

from .client import SignatureGenerationError, generate_signature
from .factory import get_signature_strategy
from .schemas import (
    SignatureHealth,
    SignatureRequestBody,
    SignatureResponse,
)

router = APIRouter(prefix="/signing", tags=["Signing"])


@router.get(
    "/health",
    response_model=SignatureHealth,
    status_code=status.HTTP_200_OK,
    summary="签名服务健康检查",
)
async def signing_health_check() -> SignatureHealth:
    strategy = get_signature_strategy()
    return await strategy.health_check()


@router.post(
    "/{platform}",
    response_model=SignatureResponse,
    status_code=status.HTTP_200_OK,
    summary="生成平台签名",
)
async def signing_generate(
    platform: str,
    request: SignatureRequestBody | None = Body(
        default=None,
        description="平台签名所需的参数",
    ),
) -> SignatureResponse:
    try:
        payload = request.payload if request else {}
        data = await generate_signature(platform, payload)
    except SignatureGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return SignatureResponse(success=True, data=data, message=None)
