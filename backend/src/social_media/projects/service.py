"""社交媒体模块的业务逻辑层"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from . import crud
from .models import SocialProject, Platform
from .schemas import SocialProjectCreate, SocialProjectUpdate, DeepAnalysisSettings


# ==================== Platform Service ====================


async def get_all_platforms(db: AsyncSession) -> List[Platform]:
    """获取所有平台（不分页，用于下拉选择）"""
    platforms, _ = await crud.get_platforms(db, skip=0, limit=100)
    return platforms


async def get_platforms_paginated(
    db: AsyncSession, page: int = 1, page_size: int = 20
) -> tuple[List[Platform], int]:
    """获取平台列表（分页）"""
    skip = (page - 1) * page_size
    return await crud.get_platforms(db, skip=skip, limit=page_size)


# ==================== SocialProject Service ====================


async def create_project(
    db: AsyncSession, project_in: SocialProjectCreate, current_user_id: int
) -> dict:
    """创建新项目（可选同时批量创建任务）"""
    # 检查项目名称是否已存在
    existing = await crud.get_project_by_name(db, project_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with name '{project_in.name}' already exists",
        )

    # 准备项目数据
    project_data = project_in.model_dump(exclude={"participant_ids", "quick_tasks"})

    # 创建项目
    project = await crud.create_project(
        db,
        project_data=project_data,
        owner_id=current_user_id,
        participant_ids=project_in.participant_ids,
    )

    # 如果提供了快速创建任务配置，批量创建任务
    created_tasks = []
    if project_in.quick_tasks:
        from src.social_media.tasks.crud import bulk_create_tasks

        # 验证平台ID是否存在
        for platform_id in project_in.quick_tasks.platform_ids:
            platform = await crud.get_platform_by_id(db, platform_id)
            if not platform:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Platform with id {platform_id} not found",
                )

        # 构建 task_params（爬虫高级选项）
        task_params = None
        if project_in.quick_tasks.data_source == "remote_crawler":
            task_params = {
                "max_notes_count": project_in.quick_tasks.max_notes_count,
                "enable_comments": 1 if project_in.quick_tasks.enable_comments else 0,
                "per_note_max_comments_count": project_in.quick_tasks.per_note_max_comments_count,
                "publish_time_type": project_in.quick_tasks.publish_time_type,
                "sort_type": project_in.quick_tasks.sort_type,
            }

        # 批量创建任务
        created_tasks = await bulk_create_tasks(
            db=db,
            project_id=project.id,
            platform_ids=project_in.quick_tasks.platform_ids,
            task_type=project_in.quick_tasks.task_type,
            data_source=project_in.quick_tasks.data_source,
            creator_id=current_user_id,
            keywords=project_in.quick_tasks.keywords,
            task_params=task_params,
            auto_analyze=(
                project_in.quick_tasks.auto_analyze
                if project_in.quick_tasks.data_source == "remote_crawler"
                else False
            ),
        )

        await db.commit()

    return {"project": project, "created_tasks": created_tasks}


async def get_project(db: AsyncSession, project_id: int) -> Optional[SocialProject]:
    """获取项目详情"""
    return await crud.get_project_by_id(db, project_id, load_relations=True)


async def get_projects_list(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    owner_id: Optional[int] = None,
    participant_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[List[SocialProject], int]:
    """获取项目列表（带过滤和分页）"""
    skip = (page - 1) * page_size
    return await crud.get_projects(
        db,
        skip=skip,
        limit=page_size,
        owner_id=owner_id,
        participant_id=participant_id,
        search=search,
    )


async def update_project(
    db: AsyncSession, project: SocialProject, project_update: SocialProjectUpdate
) -> SocialProject:
    """更新项目"""
    # 如果更新名称，检查新名称是否已被占用
    if project_update.name and project_update.name != project.name:
        existing = await crud.get_project_by_name(db, project_update.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{project_update.name}' already exists",
            )

    # 只更新提供的字段
    update_data = project_update.model_dump(exclude_unset=True)
    return await crud.update_project(db, project, update_data)


async def delete_project(db: AsyncSession, project: SocialProject) -> None:
    """删除项目"""
    await crud.delete_project(db, project)


# ==================== Project-Participant Relations ====================


async def add_participants(
    db: AsyncSession, project: SocialProject, user_ids: List[int]
) -> SocialProject:
    """为项目添加参与者"""
    # TODO: 验证用户ID是否存在（需要导入User相关模块）
    return await crud.add_participants_to_project(db, project, user_ids)


async def remove_participant(
    db: AsyncSession, project: SocialProject, user_id: int
) -> SocialProject:
    """从项目移除参与者"""
    # 不能移除owner
    if user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove project owner from participants",
        )

    # 检查用户是否是参与者
    participant_ids = [p.id for p in project.participants]
    if user_id not in participant_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} is not a participant of this project",
        )

    return await crud.remove_participant_from_project(db, project, user_id)


# ==================== Deep Analysis Settings ====================


async def update_deep_analysis_settings(
    db: AsyncSession, project: SocialProject, settings: DeepAnalysisSettings
) -> SocialProject:
    """更新项目的深度分析阈值配置"""
    project.deep_analysis_settings = settings.model_dump(exclude_unset=True)
    await db.commit()
    await db.refresh(project)
    return project


async def get_deep_analysis_settings(project: SocialProject) -> Optional[dict]:
    """获取项目的深度分析阈值配置"""
    return project.deep_analysis_settings
