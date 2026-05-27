from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from src.database import Base

if TYPE_CHECKING:
    from src.rbac.models import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(
        String(100), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)

    # 邮箱验证状态（OAuth 用户默认已验证）
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # OAuth 字段
    oauth_provider: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="OAuth provider: feishu"
    )
    oauth_open_id: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
        index=True,
        comment="OAuth provider open_id",
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="User avatar URL from OAuth provider"
    )

    # 时间戳字段
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    # 关系
    user_roles: Mapped[list["UserRole"]] = relationship(
        "src.rbac.models.UserRole", back_populates="user", cascade="all, delete-orphan"
    )
