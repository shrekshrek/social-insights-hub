"""Pydantic models used by the signing integration layer."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SignatureRequest(BaseModel):
    """Payload describing a signature generation request."""

    platform: str = Field(..., description="Target platform identifier")
    payload: Dict[str, Any] | None = Field(
        default=None, description="Platform-specific payload details"
    )


class SignatureResponse(BaseModel):
    """Standard signature response wrapper."""

    success: bool = Field(..., description="Indicates whether signing succeeded")
    data: Dict[str, Any] | None = Field(
        default=None, description="Generated signature data"
    )
    message: Optional[str] = Field(
        default=None, description="Optional diagnostic information"
    )


class SignatureHealth(BaseModel):
    """Health status for the configured signature strategy."""

    status: str = Field(..., description="ok / error / unknown")
    strategy: str = Field(..., description="Active signature strategy name")
    details: Dict[str, Any] | None = Field(
        default=None, description="Optional additional context"
    )
