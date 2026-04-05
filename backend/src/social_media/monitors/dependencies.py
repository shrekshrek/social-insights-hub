"""社交媒体模块的依赖注入"""

from fastapi import Depends, HTTPException, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.auth.models import User
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from src.rbac.utils import is_admin_or_super_admin
from . import crud
from .models import SocialMonitor, Platform


async def validate_platform_exists(
    platform_id: Annotated[int, Path()], db: AsyncSession = Depends(get_async_db)
) -> Platform:
    """验证平台是否存在"""
    platform = await crud.get_platform_by_id(db, platform_id)
    if not platform:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Platform with id {platform_id} not found",
        )
    return platform


async def validate_monitor_exists(
    monitor_id: Annotated[int, Path()], db: AsyncSession = Depends(get_async_db)
) -> SocialMonitor:
    """验证项目是否存在"""
    monitor = await crud.get_monitor_by_id(db, monitor_id, load_relations=True)
    if not monitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SocialMonitor with id {monitor_id} not found",
        )
    return monitor


async def validate_monitor_access(
    monitor: SocialMonitor = Depends(validate_monitor_exists),
    current_user: User = Depends(get_current_user),
) -> SocialMonitor:
    """
    验证用户是否有项目访问权限

    访问权限规则：
    1. 管理员和超级管理员：可以访问所有项目
    2. 项目创建者（owner）：可以访问
    3. 项目参与者（participant）：可以访问
    """
    # 管理员和超级管理员可以访问所有项目
    if is_admin_or_super_admin(current_user):
        return monitor

    # 检查是否是owner
    if monitor.owner_id == current_user.id:
        return monitor

    # 检查是否是participant
    participant_ids = [p.id for p in monitor.participants]
    if current_user.id in participant_ids:
        return monitor

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this monitor. Only the monitor owner, participants, or administrators can access this monitor.",
    )


async def validate_monitor_owner(
    monitor: SocialMonitor = Depends(validate_monitor_exists),
    current_user: User = Depends(get_current_user),
) -> SocialMonitor:
    """
    验证用户是否有项目管理权限（修改/删除）

    管理权限规则：
    1. 管理员和超级管理员：可以管理所有项目
    2. 项目创建者（owner）：可以管理自己的项目
    """
    # 管理员和超级管理员可以管理所有项目
    if is_admin_or_super_admin(current_user):
        return monitor

    # 检查是否是owner
    if monitor.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the monitor owner or administrators can perform this action",
        )
    return monitor
