"""审计日志 Pydantic Schemas"""

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import Field

from src.schemas import CustomBaseModel, PaginatedResponse

if TYPE_CHECKING:
    from src.audit.models import AuditLog


class AuditLogRead(CustomBaseModel):
    """审计日志响应"""

    id: int
    user_id: int | None = None
    username: str | None = None
    action: str
    operation: str | None = None
    resource: str | None = None
    resource_id: str | None = None
    endpoint: str | None = None
    path_template: str | None = None
    http_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    ip_address: str | None = None
    extra_data: dict | None = None
    created_at: datetime

    @classmethod
    def from_orm_with_user(cls, log: "AuditLog") -> "AuditLogRead":
        return cls(
            id=log.id,
            user_id=log.user_id,
            username=log.user.username if log.user else None,
            action=log.action,
            operation=log.operation,
            resource=log.resource,
            resource_id=log.resource_id,
            endpoint=log.endpoint,
            path_template=log.path_template,
            http_method=log.http_method,
            request_path=log.request_path,
            status_code=log.status_code,
            ip_address=log.ip_address,
            extra_data=log.extra_data,
            created_at=log.created_at,
        )


class AuditLogListResponse(PaginatedResponse[AuditLogRead]):
    """审计日志分页响应"""


class AuditLogFilterParams(CustomBaseModel):
    """查询过滤参数"""

    user_id: int | None = Field(None, description="按用户ID筛选")
    action: str | None = Field(None, description="按操作类型筛选")
    resource: str | None = Field(None, description="按资源类型筛选")
    endpoint: str | None = Field(None, description="按端点函数名筛选")
    start_time: datetime | None = Field(None, description="开始时间")
    end_time: datetime | None = Field(None, description="结束时间")
