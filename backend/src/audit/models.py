"""审计日志模型

记录用户对系统资源的所有写操作（CREATE/UPDATE/DELETE/TRIGGER）及认证事件（LOGIN/LOGOUT）。
日志不可变，无 updated_at、无软删除。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 操作者（外键 SET NULL，用户删除后保留日志）
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="操作用户ID",
    )

    # 操作语义
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="操作类型：LOGIN/LOGIN_FAILED/LOGOUT/CREATE/UPDATE/DELETE/TRIGGER",
    )
    resource: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="资源类型：social_monitor/user/strategy等",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="资源ID（路径中的数字片段）",
    )

    # HTTP 信息
    http_method: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="HTTP方法：POST/PUT/PATCH/DELETE"
    )
    request_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="请求路径"
    )
    status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="HTTP响应状态码"
    )

    # 客户端信息
    ip_address: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="客户端IP"
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="User-Agent"
    )

    # 扩展数据（脱敏后的关键参数快照）
    extra_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="请求关键参数（脱敏后）"
    )

    # 时间戳（只读，不记录 updated_at）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="记录时间",
    )

    # 关系（单向，User 不需要反向 audit_logs 集合）
    user: Mapped["User | None"] = relationship(
        "src.auth.models.User",
        foreign_keys=[user_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_audit_logs_user_action", "user_id", "action"),
        Index("idx_audit_logs_resource_id", "resource", "resource_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', resource='{self.resource}')>"
