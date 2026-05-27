from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import secrets
import logging
from datetime import timedelta

from src.auth import models, schemas
from src.exceptions import UserAlreadyExists
from src.auth.security import verify_password, pwd_context
from src.rbac import service as rbac_service
from src.rbac.models import SystemRoles, UserRole

logger = logging.getLogger(__name__)

# Redis key 前缀
EMAIL_VERIFY_PREFIX = "email_verify:"
PASSWORD_RESET_PREFIX = "password_reset:"


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
    创建新用户，注册后发送邮箱验证邮件
    """
    # Check if user already exists
    db_user = await get_user_by_username(db, username=user.username)
    if db_user:
        raise UserAlreadyExists("username", user.username)

    # 邮箱唯一性检查
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
        email_verified=False,
    )

    # Add to database
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # 分配角色
    if role_ids:
        unique_role_ids = list(dict.fromkeys(role_ids))
        await rbac_service.assign_user_roles(db, db_user.id, unique_role_ids)
    else:
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
        email_verified=True,  # OAuth 用户邮箱默认已验证
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    # 分配默认角色
    default_role = await rbac_service.get_role_by_name(db, SystemRoles.USER)
    if default_role:
        await rbac_service.assign_user_roles(db, db_user.id, [default_role.id])

    return db_user


# ========== 邮箱验证 ==========

async def create_email_verify_token(redis_client, user_id: int) -> str:
    """生成邮箱验证 token，存入 Redis"""
    from src.config import settings
    token = secrets.token_urlsafe(32)
    key = f"{EMAIL_VERIFY_PREFIX}{token}"
    await redis_client.set(key, str(user_id), ex=settings.EMAIL_VERIFY_TOKEN_EXPIRE_SECONDS)
    return token


async def verify_email_token(db: AsyncSession, redis_client, token: str) -> models.User | None:
    """验证邮箱 token，成功则标记用户邮箱已验证"""
    key = f"{EMAIL_VERIFY_PREFIX}{token}"
    user_id_bytes = await redis_client.get(key)
    if not user_id_bytes:
        return None

    user_id = int(user_id_bytes)
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.email_verified = True
    await db.commit()
    await db.refresh(user)
    await redis_client.delete(key)
    return user


# ========== 密码重置 ==========

async def create_password_reset_token(redis_client, user_id: int) -> str:
    """生成密码重置 token，存入 Redis"""
    from src.config import settings
    token = secrets.token_urlsafe(32)
    key = f"{PASSWORD_RESET_PREFIX}{token}"
    await redis_client.set(key, str(user_id), ex=settings.PASSWORD_RESET_TOKEN_EXPIRE_SECONDS)
    return token


async def reset_password_with_token(
    db: AsyncSession, redis_client, token: str, new_password: str
) -> models.User | None:
    """用重置 token 更新密码，成功返回用户"""
    key = f"{PASSWORD_RESET_PREFIX}{token}"
    user_id_bytes = await redis_client.get(key)
    if not user_id_bytes:
        return None

    user_id = int(user_id_bytes)
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()
    await db.refresh(user)
    await redis_client.delete(key)
    return user

