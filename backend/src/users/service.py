from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional, List, Tuple

from src.auth.models import User
from src.auth import schemas as auth_schemas
from src.users import schemas
from src.pagination import PaginationParams
from src.rbac import service as rbac_service
from src.auth import service as auth_service
from fastapi import HTTPException, status


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """根据ID获取用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession, pagination: PaginationParams
) -> Tuple[List[User], int]:
    """获取用户列表（分页）"""
    # 获取总数
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar()

    # 获取用户列表
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    users = list(result.scalars().all())

    return users, total


async def update_user(
    db: AsyncSession, user_id: int, user_update: schemas.UserUpdate
) -> Optional[User]:
    """更新用户信息"""
    # 获取用户
    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    # 更新字段
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "password":
            # 如果更新密码，需要哈希处理
            from src.auth.security import pwd_context

            value = pwd_context.hash(value)
            setattr(user, "hashed_password", value)
        else:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """删除用户"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return False

    await db.delete(user)
    await db.commit()
    return True


async def user_to_schema(db: AsyncSession, user: User) -> auth_schemas.UserRead:
    """将 ORM User 转为 UserRead（附带角色），避免重复的 get_user_roles + from_orm_full。"""
    user_roles = await rbac_service.get_user_roles(db, user.id)
    role_names = [role.name for role in user_roles]
    return auth_schemas.UserRead.from_orm_full(user, role_names)


async def get_user_with_roles(
    db: AsyncSession, user_id: int
) -> Optional[auth_schemas.UserRead]:
    """获取用户信息，包含角色信息"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    return await user_to_schema(db, user)


async def get_users_with_roles_batch(
    db: AsyncSession, users: List[User]
) -> List[auth_schemas.UserRead]:
    """批量获取用户信息，避免N+1查询"""
    if not users:
        return []

    user_ids = [user.id for user in users]

    # 一次查询获取所有用户的角色
    from src.rbac.models import UserRole, Role

    roles_result = await db.execute(
        select(UserRole.user_id, Role.name)
        .join(Role)
        .where(UserRole.user_id.in_(user_ids))
    )

    # 构建用户ID到角色的映射
    user_roles_map = {}
    for user_id, role_name in roles_result.all():
        if user_id not in user_roles_map:
            user_roles_map[user_id] = []
        user_roles_map[user_id].append(role_name)

    # 构造响应数据
    return [
        auth_schemas.UserRead.from_orm_full(user, user_roles_map.get(user.id, []))
        for user in users
    ]


async def create_user_admin(
    db: AsyncSession, user_create: schemas.UserAdminCreate
) -> auth_schemas.UserRead:
    """管理员创建用户，并可选分配角色"""

    role_ids: list[int] | None = None
    if user_create.role_ids:
        # 去重并验证角色是否存在
        unique_role_ids = list(dict.fromkeys(user_create.role_ids))
        role_ids = []
        for role_id in unique_role_ids:
            role = await rbac_service.get_role_by_id(db, role_id)
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"角色ID {role_id} 不存在",
                )
            role_ids.append(role_id)

    # 复用通用创建逻辑（admin 直建：信任 admin 输入的邮箱 = 已验证）
    new_user = await auth_service.create_user(
        db,
        username=user_create.username,
        password=user_create.password,
        email=user_create.email,
        email_verified=bool(user_create.email),
        role_ids=role_ids,
    )

    return await user_to_schema(db, new_user)
