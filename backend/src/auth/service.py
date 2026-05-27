import json
import logging
import secrets

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.auth import models
from src.auth.security import pwd_context, verify_password
from src.config import settings
from src.exceptions import UserAlreadyExists
from src.rbac import service as rbac_service
from src.rbac.models import SystemRoles, UserRole

logger = logging.getLogger(__name__)

# Redis key 前缀
INVITE_TOKEN_PREFIX = "invite:"
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
    db: AsyncSession,
    username: str,
    password: str,
    email: str | None = None,
    email_verified: bool = False,
    role_ids: list[int] | None = None,
) -> models.User:
    """
    创建新用户（密码登录）。

    调用方负责决定 email_verified：
    - 邀请注册：True（邀请邮件能送达即证明邮箱真实）
    - 管理员直建：调用方按场景决定（紧急兜底场景 admin 可直接信任）
    - email 可为 None，但没有邮箱的用户无法走密码重置流程
    """
    db_user = await get_user_by_username(db, username=username)
    if db_user:
        raise UserAlreadyExists("username", username)

    if email:
        db_user = await get_user_by_email(db, email=email)
        if db_user:
            raise UserAlreadyExists("email", email)

    hashed_password = pwd_context.hash(password)

    db_user = models.User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        email_verified=email_verified,
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

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


# ========== 邀请注册 token ==========


async def create_invite_token(
    redis_client,
    email: str,
    default_role_id: int | None = None,
) -> str:
    """生成邀请 token，存入 Redis。value 是 JSON {email, default_role_id?}。"""
    token = secrets.token_urlsafe(32)
    key = f"{INVITE_TOKEN_PREFIX}{token}"
    payload: dict = {"email": email}
    if default_role_id is not None:
        payload["default_role_id"] = default_role_id
    await redis_client.set(
        key,
        json.dumps(payload),
        ex=settings.INVITE_TOKEN_EXPIRE_SECONDS,
    )
    return token


async def peek_invite_token(redis_client, token: str) -> dict | None:
    """读取邀请 token payload（不消费）。无效返回 None。"""
    key = f"{INVITE_TOKEN_PREFIX}{token}"
    raw = await redis_client.get(key)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("invite token payload 解析失败：token=%s", token)
        return None
    if not isinstance(payload, dict) or "email" not in payload:
        return None
    return payload


async def consume_invite_token(redis_client, token: str) -> dict | None:
    """消费邀请 token：读取并立即删除（一次性）。返回 payload 或 None。"""
    payload = await peek_invite_token(redis_client, token)
    if payload is None:
        return None
    await redis_client.delete(f"{INVITE_TOKEN_PREFIX}{token}")
    return payload


# ========== 密码重置 ==========


async def create_password_reset_token(redis_client, user_id: int) -> str:
    """生成密码重置 token，存入 Redis（仅 admin 触发调用）。"""
    token = secrets.token_urlsafe(32)
    key = f"{PASSWORD_RESET_PREFIX}{token}"
    await redis_client.set(
        key,
        str(user_id),
        ex=settings.PASSWORD_RESET_TOKEN_EXPIRE_SECONDS,
    )
    return token


async def reset_password_with_token(
    db: AsyncSession, redis_client, token: str, new_password: str
) -> models.User | None:
    """用重置 token 更新密码，成功返回用户。token 一次性消费。"""
    key = f"{PASSWORD_RESET_PREFIX}{token}"
    user_id_bytes = await redis_client.get(key)
    if not user_id_bytes:
        return None

    try:
        user_id = int(user_id_bytes)
    except (TypeError, ValueError):
        return None

    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not user.hashed_password:
        # OAuth-only 用户不允许通过密码重置接管账号
        return None

    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()
    await db.refresh(user)
    await redis_client.delete(key)
    return user
