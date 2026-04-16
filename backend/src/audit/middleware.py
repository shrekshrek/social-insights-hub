"""审计日志中间件

拦截写操作和认证事件，异步写入 audit_logs 表。

设计原则：
- 元数据单一来源：从匹配到的 route 上读取 summary/tags/name/path（项目约定每个端点必须有 summary/tags）
- 仅捕获，不阻塞：审计写入失败不影响主请求
- fire-and-forget：用 asyncio.create_task 异步写入
- 轻量解析：仅从 JWT header 提取 username，不做完整校验
"""

import asyncio
import logging
from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.config import settings
from src.audit.service import save_audit_log

logger = logging.getLogger(__name__)

# tag → 资源类型映射（tag 是元数据单一来源）
# None 表示不对应实体资源（如认证事件），或需要按路径二次消歧
_TAG_RESOURCE_MAP: dict[str, str | None] = {
    "Authentication": None,
    "Audit": None,  # 审计自身不审计
    "Users": "user",
    "RBAC": None,  # 按路径二次消歧为 role / permission
    "Social Media - Monitors": "social_monitor",
    "Social Media - Tasks": "social_task",
    "Social Media - Analysis": "social_slice",
    "News Media - Monitors": "news_monitor",
    "News Media - Tasks": "news_task",
    "News Media - Analysis": "news_slice",
    "Strategies": "strategy",
    "Analysis Jobs": "analysis_job",
    "Knowledge Base": "kb_document",
    "Research Agent": "research_task",
}

# 不审计的 tag（审计自身）
_SKIP_TAGS = {"Audit"}

# HTTP 方法 → 默认 action
_METHOD_ACTION: dict[str, str] = {
    "POST": "CREATE",
    "PUT": "UPDATE",
    "PATCH": "UPDATE",
    "DELETE": "DELETE",
}

# 路径末段 → TRIGGER 语义
_TRIGGER_SUFFIXES = {"execute", "cancel", "analyze", "run", "refine", "approve", "retry", "preview"}

# 仅审计写方法
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _extract_username(request: Request) -> str | None:
    """从 Authorization Bearer token 中解析 username（sub 字段），失败返回 None。"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def _resolve_resource(tags: list[str], path_template: str) -> str | None:
    """通过 tag 和路径模板推断资源类型。"""
    for tag in tags:
        if tag not in _TAG_RESOURCE_MAP:
            continue
        # RBAC 歧义：路径含 /permissions 为 permission，否则 role
        if tag == "RBAC":
            return "permission" if "/permissions" in path_template else "role"
        return _TAG_RESOURCE_MAP[tag]
    return None


def _extract_last_id(path: str) -> str | None:
    """取路径中最后一个纯数字段作为 resource_id。"""
    last_id: str | None = None
    for segment in path.split("/"):
        if segment.isdigit():
            last_id = segment
    return last_id


def _determine_action(
    endpoint: str | None,
    tags: list[str],
    method: str,
    path: str,
    status_code: int,
) -> str:
    """基于 endpoint/tag/方法/路径/状态码推断 action。"""
    # 认证事件：用 endpoint 函数名精确识别（避免路径猜测）
    if "Authentication" in tags:
        if endpoint == "login":
            return "LOGIN" if status_code < 400 else "LOGIN_FAILED"
        if endpoint == "logout":
            return "LOGOUT"

    # 路径末段为触发类动词
    last_segment = path.rstrip("/").rsplit("/", 1)[-1]
    if last_segment in _TRIGGER_SUFFIXES:
        return "TRIGGER"

    return _METHOD_ACTION.get(method, "CREATE")


class AuditMiddleware(BaseHTTPMiddleware):
    """审计日志中间件：拦截写操作，从 route 元数据异步写入 audit_logs。"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method

        # 非写方法直接透传
        if method not in _WRITE_METHODS:
            return await call_next(request)

        # 提前捕获（token 在请求处理期间有效）
        username = _extract_username(request)
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        request_path = request.url.path

        response = await call_next(request)

        # 登录场景无 Bearer token，从 request.state 读取（由 /auth/token 端点设置）
        if not username:
            username = getattr(request.state, "audit_username", None)

        # 从 scope 拿匹配到的 APIRoute
        route = request.scope.get("route")
        if not isinstance(route, APIRoute):
            return response  # 404 / 非 FastAPI 路由，不审计

        tags = list(route.tags or [])
        if any(tag in _SKIP_TAGS for tag in tags):
            return response

        operation = route.summary
        endpoint = route.name
        path_template = route.path
        resource = _resolve_resource(tags, path_template)
        resource_id = _extract_last_id(request_path)
        action = _determine_action(endpoint, tags, method, request_path, response.status_code)

        asyncio.create_task(
            save_audit_log(
                username=username,
                action=action,
                operation=operation,
                resource=resource,
                resource_id=resource_id,
                endpoint=endpoint,
                path_template=path_template,
                http_method=method,
                request_path=request_path,
                status_code=response.status_code,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

        return response
