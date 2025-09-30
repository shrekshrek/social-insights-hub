from typing import Callable, List

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.rbac import service
from src.rbac.exceptions import InsufficientPermissionsException


async def require_permission(
    permission: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """
    权限检查依赖函数

    Args:
        permission: 需要的权限，如 "user:read"
        db: 数据库会话
        current_user: 当前用户

    Returns:
        当前用户（如果有权限）

    Raises:
        HTTPException: 如果没有权限
    """
    has_permission = await service.check_user_permission_cached(
        db, current_user.id, permission
    )
    if not has_permission:
        raise InsufficientPermissionsException(permission)
    return current_user


def create_permission_dependency(permission: str) -> Callable:
    """
    创建特定权限的依赖函数

    Args:
        permission: 权限名称

    Returns:
        依赖函数
    """

    async def permission_dependency(
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        return await require_permission(permission, db, current_user)

    return permission_dependency


# 数据操作权限依赖
require_user_read = create_permission_dependency("user:read")
require_user_write = create_permission_dependency("user:write")
require_user_delete = create_permission_dependency("user:delete")
require_role_read = create_permission_dependency("role:read")
require_role_write = create_permission_dependency("role:write")
require_role_delete = create_permission_dependency("role:delete")
require_permission_read = create_permission_dependency("permission:read")

# 页面访问权限依赖 - 新的命名格式
require_dashboard_access = create_permission_dependency("dashboard:access")
require_user_mgmt_access = create_permission_dependency("user_mgmt:access")
require_role_mgmt_access = create_permission_dependency("role_mgmt:access")
require_perm_mgmt_access = create_permission_dependency("perm_mgmt:access")


async def get_current_user_permissions(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    获取当前用户的所有权限

    Returns:
        权限对象列表 (结构化格式)
    """
    permissions_objs = await service.get_user_permissions_db(db, current_user.id)
    return [
        {
            "target": p.target,
            "action": p.action,
            "display_name": p.display_name,
            "description": p.description,
        }
        for p in permissions_objs
    ]


async def get_current_user_roles(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """
    获取当前用户的所有角色

    Returns:
        角色信息列表
    """
    roles = await service.get_user_roles(db, current_user.id)
    return [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles]
