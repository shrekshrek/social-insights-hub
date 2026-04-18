"""飞书 OAuth 2.0 客户端

负责与飞书开放平台 OAuth API 交互：
- 构造授权 URL
- 用 authorization code 兑换 user_access_token
- 用 user_access_token 获取用户信息
"""

import logging
import secrets
from urllib.parse import urlencode

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USERINFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

# Redis key prefix for OAuth state
OAUTH_STATE_PREFIX = "feishu_oauth_state:"
OAUTH_STATE_TTL_SECONDS = 300  # 5 minutes


def generate_state() -> str:
    """生成 CSRF 防护用的随机 state 字符串。"""
    return secrets.token_urlsafe(32)


def build_authorize_url(state: str) -> str:
    """构造飞书授权页 URL。

    Args:
        state: CSRF 防护随机串，需存入 Redis 供回调校验。

    Returns:
        完整的飞书授权页跳转 URL。
    """
    params = {
        "client_id": settings.FEISHU_APP_ID,
        "redirect_uri": settings.FEISHU_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "state": state,
    }
    return f"{FEISHU_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    """用授权码兑换 user_access_token。

    Args:
        code: 飞书回调携带的授权码（有效期 5 分钟，一次性）。

    Returns:
        飞书 token 响应，包含 access_token, expires_in 等字段。

    Raises:
        httpx.HTTPStatusError: 飞书 API 返回非 2xx。
        ValueError: 飞书 API 返回业务错误码。
    """
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.FEISHU_APP_ID,
        "client_secret": settings.FEISHU_APP_SECRET,
        "code": code,
        "redirect_uri": settings.FEISHU_OAUTH_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            FEISHU_TOKEN_URL,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        resp.raise_for_status()
        data = resp.json()

    # v2 token 接口在 HTTP 200 时仍可能返回业务错误
    if "error" in data:
        error_desc = data.get("error_description", data.get("error", "unknown"))
        logger.error("飞书 token 兑换失败: %s", data)
        raise ValueError(f"飞书授权失败: {error_desc}")

    return data


async def get_feishu_user_info(access_token: str) -> dict:
    """用 user_access_token 获取用户基本信息。

    Args:
        access_token: 飞书 user_access_token。

    Returns:
        用户信息字典，包含 open_id, name, avatar_url 等。

    Raises:
        httpx.HTTPStatusError: 飞书 API 返回非 2xx。
        ValueError: 飞书 API 返回业务错误码。
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            FEISHU_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("code", 0) != 0:
        logger.error("飞书用户信息获取失败: %s", data)
        raise ValueError(f"获取用户信息失败: {data.get('msg', 'unknown')}")

    return data.get("data", {})
