"""Agent API 依赖项"""

from fastapi import Header, HTTPException, status

from src.config import get_settings


async def verify_agent_api_key(
    authorization: str = Header(..., description="Bearer {api_key}"),
) -> bool:
    """验证 Agent API Key

    Args:
        authorization: Authorization header, format: "Bearer {api_key}"

    Returns:
        bool: True if valid

    Raises:
        HTTPException: 401 if invalid
    """
    settings = get_settings()

    if not settings.AGENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AGENT_API_KEY not configured on server",
        )

    # Extract token from "Bearer {token}"
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer {api_key}",
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    if token != settings.AGENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return True
