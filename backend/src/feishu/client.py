"""飞书消息 API 客户端

通过飞书 IM API 向策略相关用户（创建者 + 参与者）发送个人消息。
使用 tenant_access_token 以应用身份发送。
失败时只记录警告日志，不影响主业务流程。
"""

import asyncio
import logging
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

TENANT_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
SEND_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# 缓存 tenant_access_token，避免每次发消息都请求
_token_cache: dict[str, str | float] = {
    "token": "",
    "expires_at": 0.0,
}


async def _get_tenant_access_token() -> str | None:
    """获取 tenant_access_token，带内存缓存（提前 5 分钟刷新）。"""
    now = time.time()
    if _token_cache["token"] and float(_token_cache["expires_at"]) > now + 300:
        return str(_token_cache["token"])

    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                TENANT_TOKEN_URL,
                json={
                    "app_id": settings.FEISHU_APP_ID,
                    "app_secret": settings.FEISHU_APP_SECRET,
                },
            )
            data = resp.json()
            if data.get("code", -1) != 0:
                logger.warning("获取 tenant_access_token 失败: %s", data)
                return None

            token = data["tenant_access_token"]
            expire = data.get("expire", 7200)
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + expire
            return token
    except Exception as exc:
        logger.warning("获取 tenant_access_token 异常: %s", exc)
        return None


async def _send_message_to_user(open_id: str, card: dict) -> None:
    """向单个用户发送交互式卡片消息。"""
    token = await _get_tenant_access_token()
    if not token:
        return

    try:
        import json

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SEND_MESSAGE_URL}?receive_id_type=open_id",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "receive_id": open_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card),
                },
            )
            data = resp.json()
            if data.get("code", 0) != 0:
                logger.warning(
                    "飞书消息发送失败 (open_id=%s): %s", open_id, data
                )
    except Exception as exc:
        logger.warning("飞书消息发送异常 (open_id=%s): %s", open_id, exc)


async def _send_to_users(open_ids: list[str], card: dict) -> None:
    """向多个用户逐一发送消息，跳过空 open_id。"""
    for open_id in open_ids:
        if open_id:
            await _send_message_to_user(open_id, card)


def fire_notification(card: dict, open_ids: list[str]) -> None:
    """在当前 asyncio 事件循环中非阻塞地向指定用户发送飞书通知。

    Args:
        card: 飞书交互式卡片内容（传给 content 字段的 dict）。
        open_ids: 目标用户的飞书 open_id 列表。

    必须在 async 函数（FastAPI handler 或 APScheduler job）内调用。
    通知发送失败不会影响调用方的流程。
    没有绑定飞书的用户（open_id 为空）会被自动跳过。
    """
    if not settings.FEISHU_APP_ID or not open_ids:
        return
    asyncio.create_task(_send_to_users(open_ids, card))
