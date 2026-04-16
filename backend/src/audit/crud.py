"""审计日志 CRUD 操作"""

from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditLog


async def create_audit_log(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    resource: str | None = None,
    resource_id: str | None = None,
    http_method: str | None = None,
    request_path: str | None = None,
    status_code: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    extra_data: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        http_method=http_method,
        request_path=request_path,
        status_code=status_code,
        ip_address=ip_address,
        user_agent=user_agent,
        extra_data=extra_data,
    )
    db.add(log)
    await db.flush()
    return log


async def get_audit_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    action: str | None = None,
    resource: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[list[AuditLog], int]:
    """分页查询审计日志，支持多维度过滤。"""
    stmt = select(AuditLog)
    conditions = []

    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        conditions.append(AuditLog.action == action)
    if resource:
        conditions.append(AuditLog.resource == resource)
    if start_time:
        conditions.append(AuditLog.created_at >= start_time)
    if end_time:
        conditions.append(AuditLog.created_at <= end_time)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    stmt = stmt.order_by(AuditLog.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    return logs, total
