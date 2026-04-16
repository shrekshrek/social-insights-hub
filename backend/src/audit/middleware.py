"""审计日志中间件

自动拦截所有写操作（POST/PUT/PATCH/DELETE）和认证事件（登录/登出），
异步写入 audit_logs 表。

设计原则：
- 仅捕获，不阻塞：审计写入失败不影响主请求
- fire-and-forget：使用 asyncio.create_task 异步写入
- 轻量解析：只从 JWT header 提取 user_id，不做完整校验
"""

import asyncio
import logging
from typing import Callable

from fastapi import Request, Response
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.config import settings
from src.audit.service import save_audit_log

logger = logging.getLogger(__name__)

# API 路径前缀
_API_PREFIX = "/api/v1"

# 路径前缀 → 资源类型（顺序敏感：更具体的前缀放前面）
_RESOURCE_MAP: list[tuple[str, str]] = [
    ("social-media/monitors", "social_monitor"),
    ("social-media/tasks", "social_task"),
    ("social-media/analysis", "social_slice"),
    ("news-media/monitors", "news_monitor"),
    ("news-media/tasks", "news_task"),
    ("news-media/analysis", "news_slice"),
    ("strategies", "strategy"),
    ("jobs", "analysis_job"),
    ("knowledge-base", "kb_document"),
    ("users", "user"),
    ("rbac/roles", "role"),
    ("rbac/permissions", "permission"),
    ("research-agent", "research_task"),
]

# HTTP 方法 → 默认操作语义
_METHOD_ACTION: dict[str, str] = {
    "POST": "CREATE",
    "PUT": "UPDATE",
    "PATCH": "UPDATE",
    "DELETE": "DELETE",
}

# 路径后缀 → TRIGGER 语义（匹配最后一段路径）
_TRIGGER_SUFFIXES = {"execute", "cancel", "analyze", "run", "refine", "approve", "retry"}

# 不需要审计的路径前缀
_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


def _extract_username(request: Request) -> str | None:
    """从 Authorization Bearer token 中解析 username（sub 字段），失败返回 None。"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")  # sub 存的是 username 字符串
    except JWTError:
        return None


def _extract_resource(path_after_prefix: str) -> str | None:
    """根据路径前缀推断资源类型。"""
    for prefix, resource in _RESOURCE_MAP:
        if path_after_prefix.startswith(prefix):
            return resource
    return None


def _extract_resource_id(path_after_prefix: str) -> str | None:
    """提取路径中第一个数字片段作为 resource_id。"""
    for segment in path_after_prefix.split("/"):
        if segment.isdigit():
            return segment
    return None


def _determine_action(method: str, path_after_prefix: str, status_code: int) -> str:
    """根据方法、路径、状态码推断操作语义。"""
    # 认证特殊事件（/auth/token 是实际的登录端点）
    if path_after_prefix == "auth/token":
        return "LOGIN" if status_code < 400 else "LOGIN_FAILED"
    if path_after_prefix == "auth/logout":
        return "LOGOUT"

    # 路径末段为触发类操作
    last_segment = path_after_prefix.rstrip("/").rsplit("/", 1)[-1]
    if last_segment in _TRIGGER_SUFFIXES:
        return "TRIGGER"

    return _METHOD_ACTION.get(method, "CREATE")


def _should_audit(method: str, path: str) -> bool:
    """判断该请求是否需要审计。"""
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    for skip in _SKIP_PATHS:
        if path.startswith(skip):
            return False
    return True


class AuditMiddleware(BaseHTTPMiddleware):
    """审计日志中间件：拦截写操作，异步写入 audit_logs。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        # 快速跳过不需要审计的请求
        if not _should_audit(method, path):
            return await call_next(request)

        # 提前解析 username（JWT sub 字段，token 在请求处理期间仍有效）
        username = _extract_username(request)
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        # 执行实际请求
        response = await call_next(request)

        # 解析路径
        path_after_prefix = path.removeprefix(_API_PREFIX).lstrip("/")
        action = _determine_action(method, path_after_prefix, response.status_code)
        resource = _extract_resource(path_after_prefix)
        resource_id = _extract_resource_id(path_after_prefix)

        # fire-and-forget 写入审计日志
        asyncio.create_task(
            save_audit_log(
                username=username,
                action=action,
                resource=resource,
                resource_id=resource_id,
                http_method=method,
                request_path=path,
                status_code=response.status_code,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

        return response
