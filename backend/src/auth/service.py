from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.auth import models, schemas
from src.exceptions import UserAlreadyExists
from src.auth.security import verify_password, pwd_context
from src.rbac import service as rbac_service
from src.rbac.models import SystemRoles, UserRole


async def get_user_by_username(db: AsyncSession, username: str):
    """
    根据用户名获取用户（包含角色信息）
    """
    result = await db.execute(
        select(models.User)
        .options(selectinload(models.User.user_roles).selectinload(UserRole.role))
        .where(models.User.username == username)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str):
    """
    根据邮箱获取用户
    """
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_open_id(db: AsyncSession, open_id: str):
    """
    根据飞书 open_id 获取用户
    """
    result = await db.execute(
        select(models.User)
        .options(selectinload(models.User.user_roles).selectinload(UserRole.role))
        .where(models.User.oauth_open_id == open_id)
    )
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> models.User | None:
    """
    验证用户身份（仅密码登录用户）
    """
    user = await get_user_by_username(db, username=username)
    if not user:
        return None
    # 飞书用户无密码，不允许密码登录
    if not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(
    db: AsyncSession, user: schemas.UserCreate, role_ids: list[int] | None = None
):
    """
    创建新用户
    """
    # Check if user already exists
    db_user = await get_user_by_username(db, username=user.username)
    if db_user:
        raise UserAlreadyExists("username", user.username)

    # 只有当邮箱不为空时才检查唯一性
    if user.email:
        db_user = await get_user_by_email(db, email=user.email)
        if db_user:
            raise UserAlreadyExists("email", user.email)

    # Hash the password
    hashed_password = pwd_context.hash(user.password)

    # Create user instance
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
    )

    # Add to database
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # 分配角色
    if role_ids:
        # 去重保持原有顺序
        unique_role_ids = list(dict.fromkeys(role_ids))
        await rbac_service.assign_user_roles(db, db_user.id, unique_role_ids)
    else:
        # 为新用户分配默认角色 (普通用户角色)
        default_role = await rbac_service.get_role_by_name(db, SystemRoles.USER)
        if default_role:
            await rbac_service.assign_user_roles(db, db_user.id, [default_role.id])

    return db_user


async def change_password(
    db: AsyncSession, user: models.User, current_password: str, new_password: str
) -> bool:
    """
    修改用户密码

    Args:
        db: 数据库会话
        user: 当前用户
        current_password: 当前密码
        new_password: 新密码

    Returns:
        bool: 修改是否成功
    """
    # 验证当前密码
    if not verify_password(current_password, user.hashed_password):
        return False

    # 检查新密码是否与当前密码相同
    if verify_password(new_password, user.hashed_password):
        return False

    # Hash new password and update user
    hashed_password = pwd_context.hash(new_password)
    user.hashed_password = hashed_password

    await db.commit()
    await db.refresh(user)

    return True


async def get_or_create_feishu_user(
    db: AsyncSession,
    open_id: str,
    name: str,
    avatar_url: str | None,
    email: str | None,
) -> models.User:
    """
    按飞书 open_id 查找用户，不存在则自动创建。

    - 已存在：更新 avatar_url（飞书头像可能变更）后返回
    - 不存在：创建新用户，username 取飞书 name（冲突时追加随机后缀），分配默认角色
    """
    import secrets

    user = await get_user_by_open_id(db, open_id)
    if user:
        # 更新可能变化的头像
        if user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            await db.commit()
            await db.refresh(user)
        return user

    # 生成不冲突的 username
    base_name = name.lower().replace(" ", "_")[:40]
    username = base_name
    existing = await get_user_by_username(db, username)
    if existing:
        username = f"{base_name}_{secrets.token_hex(3)}"

    db_user = models.User(
        username=username,
        email=email,
        hashed_password=None,
        oauth_provider="feishu",
        oauth_open_id=open_id,
        avatar_url=avatar_url,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # 分配默认角色
    default_role = await rbac_service.get_role_by_name(db, SystemRoles.USER)
    if default_role:
        await rbac_service.assign_user_roles(db, db_user.id, [default_role.id])

    return db_user
