from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.auth.models import User


class SystemRoles:
    """系统角色常量定义"""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"

    @classmethod
    def get_all(cls) -> list[str]:
        """获取所有系统角色名称"""
        return [cls.SUPER_ADMIN, cls.ADMIN, cls.USER]

    @classmethod
    def is_core_role(cls, role_name: str) -> bool:
        """判断是否为系统核心角色"""
        return role_name in cls.get_all()


class Role(Base):
    """角色表 - 智能权限策略模型"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    permission_strategy: Mapped[str] = mapped_column(String(20), default="explicit")
    # explicit: 明确的权限列表
    # all: 拥有所有权限（超级管理员）
    # admin: 拥有除删除权限外的所有权限（管理员）

    # 关系
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    users: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class Permission(Base):
    """权限表 - 最终优化模型，语义清晰，性能最优"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(50), index=True)  # 目标模块/对象
    action: Mapped[str] = mapped_column(String(50), index=True)  # 操作类型
    display_name: Mapped[str] = mapped_column(String(100))  # 用户显示名称
    description: Mapped[str] = mapped_column(Text, nullable=True)  # 权限详细说明

    # 性能优化：复合唯一约束和索引
    __table_args__ = (
        UniqueConstraint("target", "action", name="uq_permission_target_action"),
        Index("ix_permission_target_action", "target", "action"),
    )

    # 关系
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )

    # 计算属性：权限标识符
    @property
    def permission_key(self) -> str:
        """权限唯一标识符，格式为 target:action"""
        return f"{self.target}:{self.action}"

    # 权限类型判断
    @property
    def permission_type(self) -> str:
        """权限类型：page（页面访问）, rbac_core（RBAC核心）, business（业务功能）"""
        if self.action == "access":
            return "page"
        elif self.target in ["user", "role", "permission"]:
            return "rbac_core"
        else:
            return "business"


class RolePermission(Base):
    """角色权限关联表 - 简化模型"""

    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"))

    # 关系
    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")


class UserRole(Base):
    """用户角色关联表 - 简化模型"""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="users")
