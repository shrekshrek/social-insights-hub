"""社交媒体模块API路由"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from src.pagination import get_pagination_params, PaginationParams
from src.schemas import MessageResponse

from . import schemas, service
from .dependencies import (
    validate_platform_exists,
    validate_project_exists,
    validate_project_access,
    validate_project_owner
)
from .models import SocialProject, Platform


router = APIRouter(
    prefix="/social-media",
    tags=["Social Media"],
)


# ==================== Platform APIs ====================

@router.get(
    "/platforms",
    response_model=List[schemas.PlatformRead],
    status_code=status.HTTP_200_OK,
    summary="Get all platforms",
    description="获取所有可用的社交媒体平台列表（小红书、抖音等7个平台）",
)
async def get_all_platforms(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取所有平台列表，用于前端下拉选择。

    不需要分页，返回所有可用平台。
    """
    platforms = await service.get_all_platforms(db)
    return platforms


@router.get(
    "/platforms/{platform_id}",
    response_model=schemas.PlatformRead,
    status_code=status.HTTP_200_OK,
    summary="Get platform by ID",
    description="根据ID获取平台详情",
)
async def get_platform(
    platform: Platform = Depends(validate_platform_exists),
    current_user: User = Depends(get_current_user),
):
    """根据ID获取单个平台的详细信息"""
    return platform


# ==================== Project APIs ====================

@router.post(
    "/projects",
    response_model=schemas.SocialProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new project",
    description="创建新的社交媒体数据分析项目（可选同时批量创建任务）",
)
async def create_project(
    project_in: schemas.SocialProjectCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建新项目。

    - 项目名称必须唯一
    - 可以添加其他用户作为参与者
    - 创建者自动成为项目owner
    - 可选：通过quick_tasks同时批量创建任务（仅支持search和homefeed类型）

    quick_tasks示例:
    - search任务: {"platform_ids": [1,2], "task_type": "search", "data_source": "remote_crawler", "keywords": "测试关键词"}
    - homefeed任务: {"platform_ids": [1,2], "task_type": "homefeed", "data_source": "remote_crawler"}
    """
    result = await service.create_project(db, project_in, current_user.id)

    # 构建响应
    project_dict = schemas.SocialProjectRead.model_validate(result["project"]).model_dump()
    project_dict["participant_ids"] = [p.id for p in result["project"].participants]

    # 转换任务为字典列表
    from src.task_manager.schemas import DataTaskReadWithRelations
    tasks_list = []
    for task in result["created_tasks"]:
        task_dict = DataTaskReadWithRelations.model_validate(task).model_dump()
        task_dict["project_name"] = result["project"].name
        task_dict["platform_name"] = task.platform.name if task.platform else None
        task_dict["platform_code"] = task.platform.code if task.platform else None
        task_dict["creator_username"] = task.creator.username if task.creator else None
        tasks_list.append(task_dict)

    return schemas.SocialProjectCreateResponse(
        project=schemas.SocialProjectRead(**project_dict),
        created_tasks=tasks_list
    )


@router.get(
    "/projects",
    response_model=schemas.SocialProjectListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get projects list",
    description="获取项目列表，支持过滤和分页",
)
async def get_projects(
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    owner_id: Optional[int] = Query(None, description="按owner过滤"),
    my_projects: bool = Query(False, description="只显示我参与的项目（owner或participant）"),
    search: Optional[str] = Query(None, description="搜索关键词（匹配项目名称或keywords）"),
):
    """
    获取项目列表。

    权限规则：
    - 管理员和超级管理员：可以查看所有项目
    - 普通用户：默认只能查看自己创建或参与的项目

    过滤选项：
    - my_projects=true: 显式只显示当前用户的项目
    - owner_id: 按特定owner过滤（管理员可用）
    - search: 搜索项目名称或关键词

    返回分页结果，包含owner信息和关联平台。
    """
    from .dependencies import is_admin_or_super_admin

    # 权限判断：管理员可以看到所有项目，普通用户只能看到自己的项目
    if is_admin_or_super_admin(current_user):
        # 管理员可以查看所有项目
        participant_id = None
    else:
        # 普通用户只能查看自己创建或参与的项目
        participant_id = current_user.id

    projects, total = await service.get_projects_list(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
        owner_id=owner_id,
        participant_id=participant_id,
        search=search
    )

    # 转换为带owner用户名的response
    projects_with_owner = []
    for project in projects:
        project_dict = schemas.SocialProjectRead.model_validate(project).model_dump()
        project_dict["owner_username"] = project.owner.username
        projects_with_owner.append(schemas.SocialProjectReadWithOwner(**project_dict))

    return schemas.SocialProjectListResponse.create(
        items=projects_with_owner,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/projects/{project_id}",
    response_model=schemas.SocialProjectReadWithOwner,
    status_code=status.HTTP_200_OK,
    summary="Get project by ID",
    description="获取项目详情",
)
async def get_project(
    project: SocialProject = Depends(validate_project_access),
):
    """
    获取项目详情。

    需要是项目的owner或participant才能访问。
    返回包含关联平台和参与者信息。
    """
    # 构建参与者ID列表和用户名列表
    project_dict = schemas.SocialProjectRead.model_validate(project).model_dump()
    project_dict["participant_ids"] = [p.id for p in project.participants]
    project_dict["owner_username"] = project.owner.username
    project_dict["participant_usernames"] = [p.username for p in project.participants]
    return schemas.SocialProjectReadWithOwner(**project_dict)


@router.put(
    "/projects/{project_id}",
    response_model=schemas.SocialProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Update project",
    description="更新项目信息",
)
async def update_project(
    project_update: schemas.SocialProjectUpdate,
    db: AsyncSession = Depends(get_async_db),
    project: SocialProject = Depends(validate_project_owner),
):
    """
    更新项目信息。

    只有项目owner可以更新项目。
    可以更新项目名称、描述、关键词、时间范围等。
    """
    updated_project = await service.update_project(db, project, project_update)
    project_dict = schemas.SocialProjectRead.model_validate(updated_project).model_dump()
    project_dict["participant_ids"] = [p.id for p in updated_project.participants]
    return schemas.SocialProjectRead(**project_dict)


@router.delete(
    "/projects/{project_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete project",
    description="删除项目",
)
async def delete_project(
    db: AsyncSession = Depends(get_async_db),
    project: SocialProject = Depends(validate_project_owner),
):
    """
    删除项目。

    只有项目owner可以删除项目。
    删除项目会级联删除所有关联数据（任务、原文、评论等）。
    """
    await service.delete_project(db, project)
    return MessageResponse(message=f"Project '{project.name}' deleted successfully")


# ==================== Project-Participant Management ====================

@router.post(
    "/projects/{project_id}/participants",
    response_model=schemas.SocialProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Add participants to project",
    description="为项目添加参与者",
)
async def add_participants_to_project(
    participant_assignment: schemas.ProjectParticipantAssignment,
    db: AsyncSession = Depends(get_async_db),
    project: SocialProject = Depends(validate_project_owner),
):
    """
    为项目添加一个或多个参与者。

    只有项目owner可以管理参与者。
    参与者可以查看和操作项目数据，但不能修改项目设置。
    """
    updated_project = await service.add_participants(db, project, participant_assignment.user_ids)
    project_dict = schemas.SocialProjectRead.model_validate(updated_project).model_dump()
    project_dict["participant_ids"] = [p.id for p in updated_project.participants]
    return schemas.SocialProjectRead(**project_dict)


@router.delete(
    "/projects/{project_id}/participants/{user_id}",
    response_model=schemas.SocialProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Remove participant from project",
    description="从项目移除参与者",
)
async def remove_participant_from_project(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    project: SocialProject = Depends(validate_project_owner),
):
    """
    从项目移除指定参与者。

    只有项目owner可以管理参与者。
    不能移除项目owner。
    """
    updated_project = await service.remove_participant(db, project, user_id)
    project_dict = schemas.SocialProjectRead.model_validate(updated_project).model_dump()
    project_dict["participant_ids"] = [p.id for p in updated_project.participants]
    return schemas.SocialProjectRead(**project_dict)


# ==================== Deep Analysis Settings ====================

@router.put(
    "/projects/{project_id}/deep-analysis-settings",
    response_model=schemas.SocialProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Update deep analysis settings",
    description="更新项目的深度分析阈值配置",
)
async def update_deep_analysis_settings(
    settings_update: schemas.UpdateDeepAnalysisSettings,
    db: AsyncSession = Depends(get_async_db),
    project: SocialProject = Depends(validate_project_owner),
):
    """
    更新项目的AI深度分析阈值配置。

    只有项目owner可以修改分析配置。
    配置用于控制哪些数据会进入深度分析流程。
    """
    updated_project = await service.update_deep_analysis_settings(
        db, project, settings_update.settings
    )
    project_dict = schemas.SocialProjectRead.model_validate(updated_project).model_dump()
    project_dict["participant_ids"] = [p.id for p in updated_project.participants]
    return schemas.SocialProjectRead(**project_dict)


@router.get(
    "/projects/{project_id}/deep-analysis-settings",
    response_model=schemas.DeepAnalysisSettings | None,
    status_code=status.HTTP_200_OK,
    summary="Get deep analysis settings",
    description="获取项目的深度分析阈值配置",
)
async def get_deep_analysis_settings(
    project: SocialProject = Depends(validate_project_access),
):
    """
    获取项目的AI深度分析阈值配置。

    需要是项目的owner或participant。
    如果未设置，返回null。
    """
    settings = await service.get_deep_analysis_settings(project)
    if settings:
        return schemas.DeepAnalysisSettings(**settings)
    return None
