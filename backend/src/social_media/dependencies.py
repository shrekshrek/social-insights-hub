"""社交媒体模块的依赖注入"""

from fastapi import Depends, HTTPException, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from src.auth.models import User
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from . import crud
from .models import SocialProject, Platform


def is_admin_or_super_admin(user: User) -> bool:
    """检查用户是否是管理员或超级管理员"""
    role_names = [ur.role.name for ur in user.user_roles]
    return 'admin' in role_names or 'super_admin' in role_names


async def validate_platform_exists(
    platform_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db)
) -> Platform:
    """验证平台是否存在"""
    platform = await crud.get_platform_by_id(db, platform_id)
    if not platform:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Platform with id {platform_id} not found"
        )
    return platform


async def validate_project_exists(
    project_id: Annotated[int, Path()],
    db: AsyncSession = Depends(get_async_db)
) -> SocialProject:
    """验证项目是否存在"""
    project = await crud.get_project_by_id(db, project_id, load_relations=True)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with id {project_id} not found"
        )
    return project


async def validate_project_access(
    project: SocialProject = Depends(validate_project_exists),
    current_user: User = Depends(get_current_user)
) -> SocialProject:
    """
    验证用户是否有项目访问权限

    访问权限规则：
    1. 管理员和超级管理员：可以访问所有项目
    2. 项目创建者（owner）：可以访问
    3. 项目参与者（participant）：可以访问
    """
    # 管理员和超级管理员可以访问所有项目
    if is_admin_or_super_admin(current_user):
        return project

    # 检查是否是owner
    if project.owner_id == current_user.id:
        return project

    # 检查是否是participant
    participant_ids = [p.id for p in project.participants]
    if current_user.id in participant_ids:
        return project

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have access to this project. Only the project owner, participants, or administrators can access this project."
    )


async def validate_project_owner(
    project: SocialProject = Depends(validate_project_exists),
    current_user: User = Depends(get_current_user)
) -> SocialProject:
    """
    验证用户是否有项目管理权限（修改/删除）

    管理权限规则：
    1. 管理员和超级管理员：可以管理所有项目
    2. 项目创建者（owner）：可以管理自己的项目
    """
    # 管理员和超级管理员可以管理所有项目
    if is_admin_or_super_admin(current_user):
        return project

    # 检查是否是owner
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or administrators can perform this action"
        )
    return project
