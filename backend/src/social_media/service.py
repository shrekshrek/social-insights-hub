"""社交媒体模块的业务逻辑层"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from . import crud
from .models import SocialProject, Platform
from .schemas import (
    SocialProjectCreate,
    SocialProjectUpdate,
    DeepAnalysisSettings
)


# ==================== Platform Service ====================

async def get_all_platforms(db: AsyncSession) -> List[Platform]:
    """获取所有平台（不分页，用于下拉选择）"""
    platforms, _ = await crud.get_platforms(db, skip=0, limit=100)
    return platforms


async def get_platforms_paginated(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20
) -> tuple[List[Platform], int]:
    """获取平台列表（分页）"""
    skip = (page - 1) * page_size
    return await crud.get_platforms(db, skip=skip, limit=page_size)


# ==================== SocialProject Service ====================

async def create_project(
    db: AsyncSession,
    project_in: SocialProjectCreate,
    current_user_id: int
) -> SocialProject:
    """创建新项目"""
    # 检查项目名称是否已存在
    existing = await crud.get_project_by_name(db, project_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with name '{project_in.name}' already exists"
        )

    # 验证平台ID是否存在
    if project_in.platform_ids:
        for platform_id in project_in.platform_ids:
            platform = await crud.get_platform_by_id(db, platform_id)
            if not platform:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Platform with id {platform_id} not found"
                )

    # 准备项目数据
    project_data = project_in.model_dump(exclude={"platform_ids", "participant_ids"})

    # 创建项目
    project = await crud.create_project(
        db,
        project_data=project_data,
        owner_id=current_user_id,
        platform_ids=project_in.platform_ids,
        participant_ids=project_in.participant_ids
    )

    return project


async def get_project(
    db: AsyncSession,
    project_id: int
) -> Optional[SocialProject]:
    """获取项目详情"""
    return await crud.get_project_by_id(db, project_id, load_relations=True)


async def get_projects_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    owner_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    search: Optional[str] = None
) -> tuple[List[SocialProject], int]:
    """获取项目列表（带过滤和分页）"""
    skip = (page - 1) * page_size
    return await crud.get_projects(
        db,
        skip=skip,
        limit=page_size,
        owner_id=owner_id,
        participant_id=participant_id,
        search=search
    )


async def update_project(
    db: AsyncSession,
    project: SocialProject,
    project_update: SocialProjectUpdate
) -> SocialProject:
    """更新项目"""
    # 如果更新名称，检查新名称是否已被占用
    if project_update.name and project_update.name != project.name:
        existing = await crud.get_project_by_name(db, project_update.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{project_update.name}' already exists"
            )

    # 只更新提供的字段
    update_data = project_update.model_dump(exclude_unset=True)
    return await crud.update_project(db, project, update_data)


async def delete_project(
    db: AsyncSession,
    project: SocialProject
) -> None:
    """删除项目"""
    await crud.delete_project(db, project)


# ==================== Project-Platform Relations ====================

async def add_platforms(
    db: AsyncSession,
    project: SocialProject,
    platform_ids: List[int]
) -> SocialProject:
    """为项目添加平台"""
    # 验证平台ID是否存在
    for platform_id in platform_ids:
        platform = await crud.get_platform_by_id(db, platform_id)
        if not platform:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Platform with id {platform_id} not found"
            )

    return await crud.add_platforms_to_project(db, project, platform_ids)


async def remove_platform(
    db: AsyncSession,
    project: SocialProject,
    platform_id: int
) -> SocialProject:
    """从项目移除平台"""
    # 检查平台是否关联到项目
    platform_ids = [p.id for p in project.platforms]
    if platform_id not in platform_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Platform {platform_id} is not associated with this project"
        )

    return await crud.remove_platform_from_project(db, project, platform_id)


# ==================== Project-Participant Relations ====================

async def add_participants(
    db: AsyncSession,
    project: SocialProject,
    user_ids: List[int]
) -> SocialProject:
    """为项目添加参与者"""
    # TODO: 验证用户ID是否存在（需要导入User相关模块）
    return await crud.add_participants_to_project(db, project, user_ids)


async def remove_participant(
    db: AsyncSession,
    project: SocialProject,
    user_id: int
) -> SocialProject:
    """从项目移除参与者"""
    # 不能移除owner
    if user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove project owner from participants"
        )

    # 检查用户是否是参与者
    participant_ids = [p.id for p in project.participants]
    if user_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a participant of this project"
        )

    return await crud.remove_participant_from_project(db, project, user_id)


# ==================== Deep Analysis Settings ====================

async def update_deep_analysis_settings(
    db: AsyncSession,
    project: SocialProject,
    settings: DeepAnalysisSettings
) -> SocialProject:
    """更新项目的深度分析阈值配置"""
    project.deep_analysis_settings = settings.model_dump(exclude_unset=True)
    await db.commit()
    await db.refresh(project)
    return project


async def get_deep_analysis_settings(
    project: SocialProject
) -> Optional[dict]:
    """获取项目的深度分析阈值配置"""
    return project.deep_analysis_settings
