from __future__ import annotations

from typing import TYPE_CHECKING, Optional, List

from pydantic import Field, computed_field

from src.schemas import CustomBaseModel, PaginatedResponse

if TYPE_CHECKING:
    from src.rbac.models import Role


# Permission schemas - 基于target+action的最终设计
class PermissionBase(CustomBaseModel):
    target: str = Field(..., description="目标模块/对象，如：user, dashboard, reports")
    action: str = Field(..., description="操作类型，如：read, write, delete, access")
    display_name: str = Field(..., description="权限显示名称")
    description: Optional[str] = Field(None, description="权限详细描述")


class PermissionCreate(PermissionBase):
    """创建权限的数据模型（仅用于内部初始化）"""

    pass


class PermissionRead(PermissionBase):
    id: int

    @computed_field
    @property
    def permission_key(self) -> str:
        """权限标识符，格式为 target:action"""
        return f"{self.target}:{self.action}"

    @computed_field
    @property
    def permission_type(self) -> str:
        """权限类型：page（页面访问）, rbac_core（RBAC核心）, business（业务功能）"""
        if self.action == "access":
            return "page"
        elif self.target in ["user", "role", "permission"]:
            return "rbac_core"
        else:
            return "business"


# Role schemas
class RoleBase(CustomBaseModel):
    name: str = Field(..., description="角色名称")
    display_name: str = Field(..., description="角色显示名称")
    description: Optional[str] = Field(None, description="角色描述")
    permission_strategy: str = Field(
        default="explicit", description="权限策略：explicit/all/admin"
    )


class RoleCreate(RoleBase):
    permission_ids: List[int] = Field(default=[], description="权限ID列表")


class RoleUpdate(CustomBaseModel):
    display_name: Optional[str] = Field(None, description="角色显示名称")
    description: Optional[str] = Field(None, description="角色描述")
    permission_ids: Optional[List[int]] = Field(None, description="权限ID列表")


class RoleRead(RoleBase):
    id: int
    permissions: List[PermissionRead] = Field(
        default=[], description="角色拥有的权限列表"
    )

    @computed_field
    @property
    def is_core_role(self) -> bool:
        """是否为RBAC核心角色"""
        from .models import SystemRoles

        return SystemRoles.is_core_role(self.name)

    @classmethod
    def from_orm_full(cls, role: "Role") -> "RoleRead":
        """从 ORM Role 构造，处理 role_permissions 关联。
        要求 role.role_permissions 已预加载（selectinload）。
        """
        permissions = [rp.permission for rp in role.role_permissions]
        return cls(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            permission_strategy=role.permission_strategy,
            permissions=permissions,
        )


# User Role schemas
class UserRoleAssign(CustomBaseModel):
    role_ids: List[int] = Field(..., description="要分配的角色ID列表")


# Role Permission schemas
class RolePermissionAssign(CustomBaseModel):
    permission_ids: List[int] = Field(..., description="要分配的权限ID列表")


# 使用统一的分页响应格式
RoleListResponse = PaginatedResponse[RoleRead]
PermissionListResponse = PaginatedResponse[PermissionRead]

# 使用统一的消息响应（替代自定义响应）
# 不再需要 UserRoleResponse 和 RolePermissionResponse
# 统一使用 MessageResponse from src.schemas
