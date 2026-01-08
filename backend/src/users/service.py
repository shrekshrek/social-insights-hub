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


async def get_user_with_roles(
    db: AsyncSession, user_id: int
) -> Optional[auth_schemas.UserRead]:
    """获取用户信息，包含角色信息"""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None

    # 获取用户的角色信息
    user_roles = await rbac_service.get_user_roles(db, user.id)
    role_names = [role.name for role in user_roles]

    # 构造包含角色信息的用户数据
    # 使用统一的转换函数
    return convert_user_to_schema(user, role_names)


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
    result = []
    for user in users:
        role_names = user_roles_map.get(user.id, [])
        result.append(convert_user_to_schema(user, role_names))

    return result


def convert_user_to_schema(user: User, role_names: List[str]) -> auth_schemas.UserRead:
    """统一的用户数据转换工具函数（公开）"""
    return auth_schemas.UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=role_names,
    )


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

    # 复用通用创建逻辑
    new_user = await auth_service.create_user(
        db,
        auth_schemas.UserCreate(
            username=user_create.username,
            email=user_create.email,
            password=user_create.password,
        ),
        role_ids=role_ids,
    )

    user_roles = await rbac_service.get_user_roles(db, new_user.id)
    role_names = [role.name for role in user_roles]
    return convert_user_to_schema(new_user, role_names)
