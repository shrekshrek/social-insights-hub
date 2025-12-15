import json
from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.models import User
from src.pagination import PaginationParams
from src.rbac import models, schemas
from src.rbac.models import SystemRoles
from src.rbac.exceptions import (
    RoleAlreadyExistsException,
    RoleNotDeletableException,
    PermissionAlreadyExistsException,
)


# 缓存配置
class _CacheConfig:
    """内部缓存配置"""

    KEY_USER_PERMISSIONS = "rbac:user_permissions:{user_id}"
    TTL_PERMISSIONS = 600  # 10分钟

    @classmethod
    def user_permissions_key(cls, user_id: int) -> str:
        """生成用户权限缓存键"""
        return cls.KEY_USER_PERMISSIONS.format(user_id=user_id)


# 工具函数
def _parse_permission_key(permission_key: str) -> tuple[str, str]:
    """解析权限键 'target:action'"""
    if ":" not in permission_key:
        raise ValueError(f"Invalid permission key: {permission_key}")
    return permission_key.split(":", 1)


def _check_permission_in_list(
    permissions: List[dict], target: str, action: str
) -> bool:
    """检查权限是否在列表中"""
    return any(
        p.get("target") == target and p.get("action") == action for p in permissions
    )


# Permission service functions
async def get_permission_by_id(
    db: AsyncSession, permission_id: int
) -> Optional[models.Permission]:
    """根据ID获取权限"""
    result = await db.execute(
        select(models.Permission).where(models.Permission.id == permission_id)
    )
    return result.scalar_one_or_none()


async def get_permission_by_target_action(
    db: AsyncSession, target: str, action: str
) -> Optional[models.Permission]:
    """根据target和action获取权限"""
    result = await db.execute(
        select(models.Permission).where(
            models.Permission.target == target, models.Permission.action == action
        )
    )
    return result.scalar_one_or_none()


async def get_permissions(
    db: AsyncSession, pagination: PaginationParams
) -> tuple[List[models.Permission], int]:
    """获取权限列表"""
    # 获取总数
    count_result = await db.execute(select(func.count(models.Permission.id)))
    total = count_result.scalar()

    # 获取分页数据 - 按target和action排序
    result = await db.execute(
        select(models.Permission)
        .order_by(models.Permission.target, models.Permission.action)
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    permissions = result.scalars().all()

    return list(permissions), total


async def create_permission(
    db: AsyncSession, permission: schemas.PermissionCreate
) -> models.Permission:
    """创建权限（仅用于内部初始化，不暴露API）"""
    # 检查权限是否已存在
    existing = await get_permission_by_target_action(
        db, permission.target, permission.action
    )
    if existing:
        permission_key = f"{permission.target}:{permission.action}"
        raise PermissionAlreadyExistsException(permission_key)

    db_permission = models.Permission(**permission.model_dump())
    db.add(db_permission)
    await db.commit()
    await db.refresh(db_permission)
    return db_permission


# Role service functions
async def get_role_by_id(db: AsyncSession, role_id: int) -> Optional[models.Role]:
    """根据ID获取角色"""
    result = await db.execute(
        select(models.Role)
        .options(
            selectinload(models.Role.role_permissions).selectinload(
                models.RolePermission.permission
            )
        )
        .where(models.Role.id == role_id)
    )
    return result.scalar_one_or_none()


async def get_role_by_name(db: AsyncSession, name: str) -> Optional[models.Role]:
    """根据名称获取角色"""
    result = await db.execute(select(models.Role).where(models.Role.name == name))
    return result.scalar_one_or_none()


async def get_roles(
    db: AsyncSession, pagination: PaginationParams
) -> tuple[List[models.Role], int]:
    """获取角色列表"""
    # 获取总数
    count_result = await db.execute(select(func.count(models.Role.id)))
    total = count_result.scalar()

    # 获取分页数据
    result = await db.execute(
        select(models.Role)
        .options(
            selectinload(models.Role.role_permissions).selectinload(
                models.RolePermission.permission
            )
        )
        .order_by(models.Role.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    roles = result.scalars().all()

    return list(roles), total


async def create_role(db: AsyncSession, role: schemas.RoleCreate) -> models.Role:
    """创建角色"""
    # 检查角色是否已存在
    existing = await get_role_by_name(db, role.name)
    if existing:
        raise RoleAlreadyExistsException(role.name)

    # 创建角色
    role_data = role.model_dump(exclude={"permission_ids"})
    db_role = models.Role(**role_data)
    db.add(db_role)
    await db.flush()  # 获取角色ID

    # 添加权限关联
    for permission_id in role.permission_ids:
        role_permission = models.RolePermission(
            role_id=db_role.id, permission_id=permission_id
        )
        db.add(role_permission)

    await db.commit()
    await db.refresh(db_role)
    return db_role


async def update_role(
    db: AsyncSession, role_id: int, role: schemas.RoleUpdate
) -> Optional[models.Role]:
    """更新角色 - 简化版本"""
    db_role = await get_role_by_id(db, role_id)
    if not db_role:
        return None

    # 核心角色只能修改显示名称和描述，不能修改权限
    from .models import SystemRoles

    if SystemRoles.is_core_role(db_role.name):
        # 只允许修改显示名称和描述
        if role.display_name is not None:
            db_role.display_name = role.display_name
        if role.description is not None:
            db_role.description = role.description
    else:
        # 自定义角色可以修改所有字段
        for field, value in role.model_dump(
            exclude_unset=True, exclude={"permission_ids"}
        ).items():
            setattr(db_role, field, value)

        # 更新权限关联
        if role.permission_ids is not None:
            # 删除现有权限关联
            await db.execute(
                delete(models.RolePermission).where(
                    models.RolePermission.role_id == role_id
                )
            )

            # 添加新的权限关联
            for permission_id in role.permission_ids:
                role_permission = models.RolePermission(
                    role_id=role_id, permission_id=permission_id
                )
                db.add(role_permission)

    await db.commit()
    await db.refresh(db_role)
    return db_role


async def delete_role(db: AsyncSession, role_id: int) -> bool:
    """删除角色"""
    db_role = await get_role_by_id(db, role_id)
    if not db_role:
        return False

    # 检查是否为核心角色，核心角色不可删除
    if SystemRoles.is_core_role(db_role.name):
        raise RoleNotDeletableException(db_role.name, "Core roles cannot be deleted")

    await db.delete(db_role)
    await db.commit()
    return True


# User Role service functions
async def get_user_roles(db: AsyncSession, user_id: int) -> List[models.Role]:
    """获取用户的角色列表"""
    result = await db.execute(
        select(models.Role)
        .join(models.UserRole)
        .where(models.UserRole.user_id == user_id)
        .options(
            selectinload(models.Role.role_permissions).selectinload(
                models.RolePermission.permission
            )
        )
    )
    return list(result.scalars().all())


async def assign_user_roles(
    db: AsyncSession, user_id: int, role_ids: List[int]
) -> bool:
    """为用户分配角色"""
    # 检查用户是否存在
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return False

    # 删除现有角色关联
    await db.execute(delete(models.UserRole).where(models.UserRole.user_id == user_id))

    # 添加新的角色关联
    for role_id in role_ids:
        user_role = models.UserRole(user_id=user_id, role_id=role_id)
        db.add(user_role)

    await db.commit()

    # 清除用户权限缓存
    await clear_user_permissions_cache(user_id)

    return True


async def get_user_permissions_db(
    db: AsyncSession, user_id: int
) -> List[models.Permission]:
    """获取用户的所有权限（智能权限策略版本）"""
    # 获取用户的所有角色及其权限策略
    roles_result = await db.execute(
        select(models.Role)
        .join(models.UserRole)
        .where(models.UserRole.user_id == user_id)
    )
    user_roles = roles_result.scalars().all()

    # 检查智能权限策略
    for role in user_roles:
        if role.permission_strategy == "all":
            # 超级管理员：返回所有权限
            all_permissions_result = await db.execute(
                select(models.Permission).order_by(
                    models.Permission.target, models.Permission.action
                )
            )
            return list(all_permissions_result.scalars().all())

        elif role.permission_strategy == "admin":
            # 管理员：返回除核心删除外的所有权限
            admin_permissions_result = await db.execute(
                select(models.Permission)
                .where(
                    ~(
                        (models.Permission.target.in_(["user", "role", "permission"]))
                        & (models.Permission.action == "delete")
                    )
                )
                .order_by(models.Permission.target, models.Permission.action)
            )
            return list(admin_permissions_result.scalars().all())

    # 对于explicit策略的角色，使用原有的子查询逻辑
    subquery = (
        select(models.RolePermission.permission_id)
        .select_from(models.UserRole)
        .join(
            models.RolePermission,
            models.UserRole.role_id == models.RolePermission.role_id,
        )
        .where(models.UserRole.user_id == user_id)
    )

    result = await db.execute(
        select(models.Permission)
        .where(models.Permission.id.in_(subquery))
        .order_by(models.Permission.target, models.Permission.action)
    )
    return list(result.scalars().all())


async def check_user_permission_by_target_action(
    db: AsyncSession, user_id: int, target: str, action: str
) -> bool:
    """检查用户是否有指定权限 - 智能权限策略版本"""
    # 获取用户的所有角色及其权限策略
    roles_result = await db.execute(
        select(models.Role)
        .join(models.UserRole)
        .where(models.UserRole.user_id == user_id)
    )
    user_roles = roles_result.scalars().all()

    # 检查智能权限策略
    for role in user_roles:
        if role.permission_strategy == "all":
            return True  # 超级管理员拥有所有权限

        elif role.permission_strategy == "admin":
            # 管理员拥有除删除权限外的所有权限
            if action != "delete":
                return True
            # 删除权限需要检查是否为核心资源
            if target in ["user", "role", "permission"] and action == "delete":
                continue  # 管理员不能删除核心资源
            return True  # 管理员可以删除其他资源

    # 对于explicit策略的角色，使用传统权限检查
    exists_query = (
        select(1)
        .select_from(models.UserRole)
        .join(
            models.RolePermission,
            models.UserRole.role_id == models.RolePermission.role_id,
        )
        .join(
            models.Permission,
            models.RolePermission.permission_id == models.Permission.id,
        )
        .where(
            models.UserRole.user_id == user_id,
            models.Permission.target == target,
            models.Permission.action == action,
        )
    )

    result = await db.execute(select(exists_query.exists()))
    return result.scalar()


async def check_user_permission(
    db: AsyncSession, user_id: int, permission_name: str
) -> bool:
    """检查用户是否有指定权限（格式: target:action）- 包装器函数"""
    if ":" not in permission_name:
        return False
    target, action = permission_name.split(":", 1)
    return await check_user_permission_by_target_action(db, user_id, target, action)


# Role Permission service functions
async def get_role_permissions(
    db: AsyncSession, role_id: int
) -> List[models.Permission]:
    """获取角色的权限列表"""
    result = await db.execute(
        select(models.Permission)
        .join(models.RolePermission)
        .where(models.RolePermission.role_id == role_id)
        .order_by(models.Permission.target, models.Permission.action)
    )
    return list(result.scalars().all())


async def assign_role_permissions(
    db: AsyncSession, role_id: int, permission_ids: List[int]
) -> bool:
    """为角色分配权限（替换式）"""
    # 检查角色是否存在
    db_role = await get_role_by_id(db, role_id)
    if not db_role:
        return False

    # 删除现有权限关联
    await db.execute(
        delete(models.RolePermission).where(models.RolePermission.role_id == role_id)
    )

    # 添加新的权限关联
    for permission_id in permission_ids:
        role_permission = models.RolePermission(
            role_id=role_id, permission_id=permission_id
        )
        db.add(role_permission)

    await db.commit()

    # 清除所有拥有此角色的用户的权限缓存
    users_with_role = await get_users_with_role(db, role_id)
    for user in users_with_role:
        await clear_user_permissions_cache(user.id)

    return True


# ============================================================================
# 权限检查缓存优化
# ============================================================================


async def get_user_permissions_cached(db: AsyncSession, user_id: int) -> List[dict]:
    """获取用户权限（带Redis缓存，10分钟过期，结构化格式）"""
    from src.redis_client import get_redis_client

    cache_key = _CacheConfig.user_permissions_key(user_id)

    # 尝试从Redis获取缓存
    try:
        async for redis_client in get_redis_client():
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
    except Exception:
        pass  # 缓存失败时降级为数据库查询

    # 数据库查询
    permissions = await get_user_permissions_db(db, user_id)
    permission_data = [
        {
            "target": p.target,
            "action": p.action,
            "display_name": p.display_name,
            "description": p.description,
        }
        for p in permissions
    ]

    # 写入缓存
    try:
        async for redis_client in get_redis_client():
            await redis_client.setex(
                cache_key, _CacheConfig.TTL_PERMISSIONS, json.dumps(permission_data)
            )
    except Exception:
        pass  # 缓存写入失败不影响功能

    return permission_data


async def check_user_permission_cached(
    db: AsyncSession, user_id: int, permission: str
) -> bool:
    """优化版权限检查（使用缓存）- 重构版本"""
    # 先尝试从缓存获取用户权限列表
    user_permissions = await get_user_permissions_cached(db, user_id)

    # 解析权限键
    try:
        target, action = _parse_permission_key(permission)
    except ValueError:
        return False

    # 直接检查权限是否在缓存的权限列表中
    return _check_permission_in_list(user_permissions, target, action)


async def clear_user_permissions_cache(user_id: int):
    """清除用户权限缓存"""
    from src.redis_client import get_redis_client

    try:
        async for redis_client in get_redis_client():
            cache_key = _CacheConfig.user_permissions_key(user_id)
            await redis_client.delete(cache_key)
    except Exception:
        pass


async def get_users_with_role(db: AsyncSession, role_id: int) -> List[User]:
    """获取拥有指定角色的用户列表"""
    result = await db.execute(
        select(User).join(models.UserRole).where(models.UserRole.role_id == role_id)
    )
    return list(result.scalars().all())


# ============================================================================
# 内部工具函数
# ============================================================================


def _convert_role_to_schema(role: models.Role) -> schemas.RoleRead:
    """内部工具函数：将Role模型转换为RoleRead schema"""
    permissions = [rp.permission for rp in role.role_permissions]
    return schemas.RoleRead(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        permission_strategy=role.permission_strategy,
        permissions=permissions,
    )


def _convert_roles_to_schemas(roles: List[models.Role]) -> List[schemas.RoleRead]:
    """批量转换角色列表"""
    return [_convert_role_to_schema(role) for role in roles]
