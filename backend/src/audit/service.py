"""审计日志写入服务

使用独立 db session，避免影响主请求事务。
由中间件以 fire-and-forget 方式调用。

JWT sub 字段存的是 username，所以 service 负责将 username 解析为 user_id。
"""

import logging

from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.audit.crud import create_audit_log

logger = logging.getLogger(__name__)


async def _resolve_user_id(username: str | None) -> int | None:
    """将 username 解析为 user_id，找不到返回 None。"""
    if not username:
        return None
    try:
        from src.auth.models import User
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User.id).where(User.username == username))
            return result.scalar_one_or_none()
    except Exception as exc:
        logger.error("Failed to resolve user_id for username=%s: %s", username, exc)
        return None


async def save_audit_log(
    username: str | None,
    action: str,
    operation: str | None = None,
    resource: str | None = None,
    resource_id: str | None = None,
    endpoint: str | None = None,
    path_template: str | None = None,
    http_method: str | None = None,
    request_path: str | None = None,
    status_code: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra_data: dict | None = None,
) -> None:
    """写入一条审计日志，异常只记录不上抛。"""
    try:
        user_id = await _resolve_user_id(username)
        async with AsyncSessionLocal() as db:
            await create_audit_log(
                db=db,
                user_id=user_id,
                action=action,
                operation=operation,
                resource=resource,
                resource_id=resource_id,
                endpoint=endpoint,
                path_template=path_template,
                http_method=http_method,
                request_path=request_path,
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                extra_data=extra_data,
            )
            await db.commit()
    except Exception as exc:
        logger.error("Failed to save audit log: %s", exc)
