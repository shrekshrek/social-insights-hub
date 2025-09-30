from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth import models, schemas
from src.exceptions import UserAlreadyExists
from src.auth.security import verify_password, pwd_context
from src.rbac import service as rbac_service
from src.rbac.models import SystemRoles


async def get_user_by_username(db: AsyncSession, username: str):
    """
    根据用户名获取用户
    """
    result = await db.execute(
        select(models.User).where(models.User.username == username)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str):
    """
    根据邮箱获取用户
    """
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> models.User | None:
    """
    验证用户身份
    """
    user = await get_user_by_username(db, username=username)
    if not user:
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
