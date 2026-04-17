"""审计日志查询路由

端点：
- GET /audit/logs     分页查询审计日志（仅管理员可访问）
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.rbac.dependencies import require_audit_read
from src.audit import crud, schemas

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/logs",
    response_model=schemas.AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="查询审计日志",
    description="分页查询用户操作日志，支持按用户、操作类型、资源类型和时间范围筛选。仅管理员可访问。",
)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    user_id: int | None = Query(None, description="按用户ID筛选"),
    action: str | None = Query(None, description="按操作类型筛选（LOGIN/LOGIN_FAILED/CREATE/UPDATE/DELETE/TRIGGER）"),
    resource: str | None = Query(None, description="按资源类型筛选（user/social_monitor等）"),
    start_time: datetime | None = Query(None, description="开始时间"),
    end_time: datetime | None = Query(None, description="结束时间"),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_audit_read),
):
    logs, total = await crud.get_audit_logs(
        db=db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        action=action,
        resource=resource,
        start_time=start_time,
        end_time=end_time,
    )
    items = [schemas.AuditLogRead.from_orm_with_user(log) for log in logs]
    return schemas.AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
