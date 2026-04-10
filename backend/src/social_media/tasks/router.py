"""社交媒体数据任务API路由"""

from typing import Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.dependencies import get_current_user
from src.database import get_async_db
from src.pagination import get_pagination_params, PaginationParams
from src.schemas import MessageResponse

from src.social_media.monitors.dependencies import validate_monitor_exists
from src.social_media.monitors.models import SocialMonitor

from . import schemas, service
from .dependencies import validate_task_access, validate_task_owner
from .models import SocialTask



router = APIRouter(
    prefix="/social-media",
    tags=["Social Media - Tasks"],
)


# ==================== Task Management APIs ====================


@router.post(
    "/monitors/{monitor_id}/tasks",
    response_model=schemas.SocialTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create new task under a monitor",
    description="在指定监测项目下创建新的社交媒体数据采集任务",
)
async def create_task(
    task_in: schemas.SocialTaskCreate,
    monitor: SocialMonitor = Depends(validate_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建新任务（monitor_id 通过 URL 路径传递）。

    支持两种数据源：
    - remote_crawler: 通过 Agent API 由外部爬虫认领并执行
    - local_upload: 本地 JSON 文件上传

    需要项目访问权限（owner 或 participant）。
    """
    task = await service.create_task(db, monitor.id, task_in, current_user.id)
    return task


@router.get(
    "/tasks",
    response_model=schemas.DataTaskListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get tasks list",
    description="获取任务列表，支持过滤和分页",
)
async def get_tasks(
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    monitor_id: Optional[int] = Query(None, description="按项目过滤"),
    platform_id: Optional[int] = Query(None, description="按平台过滤"),
    task_type: Optional[str] = Query(None, description="按任务类型过滤"),
    status: Optional[str] = Query(None, description="按状态过滤"),
    data_source: Optional[str] = Query(None, description="按数据源过滤"),
    creator_id: Optional[int] = Query(None, description="按创建者过滤"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    phase: Optional[str] = Query(None, description="按采集阶段过滤: probe / collect"),
):
    """
    获取任务列表。

    过滤选项：
    - monitor_id: 按项目过滤（需要有项目访问权限）
    - platform_id: 按平台过滤
    - task_type: search/detail/creator/homefeed
    - status: pending/running/completed/failed
    - data_source: remote_crawler/local_upload
    - creator_id: 按创建者过滤
    - search: 搜索任务名称、描述或关键词

    返回分页结果，包含项目、平台和创建者信息。
    """
    tasks, total = await service.get_tasks_list(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
        monitor_id=monitor_id,
        platform_id=platform_id,
        task_type=task_type,
        status=status,
        data_source=data_source,
        creator_id=creator_id,
        search=search,
        current_user_id=current_user.id,
        phase=phase,
    )

    # 批量查询各任务最新 LLM 分析 Job 状态（用于判断"分析中"，避免 N+1）
    from sqlalchemy import select as sa_select
    from src.jobs.models import AnalysisJob

    task_ids = [t.id for t in tasks]
    latest_job_map: dict[int, str] = {}
    if task_ids:
        job_rows = (await db.execute(
            sa_select(AnalysisJob.social_task_id, AnalysisJob.status)
            .where(AnalysisJob.social_task_id.in_(task_ids))
            .order_by(AnalysisJob.created_at.desc())
        )).all()
        for row in job_rows:
            if row.social_task_id not in latest_job_map:
                latest_job_map[int(row.social_task_id)] = row.status

    # 转换为带关联信息的response
    tasks_with_relations = []
    for task in tasks:
        task_dict = schemas.SocialTaskRead.model_validate(task).model_dump()
        task_dict["monitor_name"] = task.monitor.name if task.monitor else None
        task_dict["platform_name"] = task.platform.name if task.platform else None
        task_dict["platform_code"] = task.platform.code if task.platform else None
        task_dict["creator_username"] = task.creator.username if task.creator else None
        # analysis_result_at 不为空表示聚合已完成；否则取最新 LLM Job 状态
        if task.analysis_result_at:
            task_dict["aggregation_status"] = "completed"
        else:
            task_dict["aggregation_status"] = latest_job_map.get(task.id)
        tasks_with_relations.append(schemas.SocialTaskReadWithRelations(**task_dict))

    return schemas.DataTaskListResponse.create(
        items=tasks_with_relations,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=schemas.SocialTaskReadWithRelations,
    status_code=status.HTTP_200_OK,
    summary="Get task by ID",
    description="获取任务详情",
)
async def get_task(
    task: SocialTask = Depends(validate_task_access),
    db: AsyncSession = Depends(get_async_db),
):
    """
    获取任务详情。

    需要项目访问权限（owner或participant）。
    """
    # analysis_result_at 不为空表示聚合已完成；否则取最新 LLM Job 状态
    from sqlalchemy import select as sa_select
    from src.jobs.models import AnalysisJob

    if task.analysis_result_at:
        aggregation_status = "completed"
    else:
        aggregation_status = (await db.execute(
            sa_select(AnalysisJob.status)
            .where(AnalysisJob.social_task_id == task.id)
            .order_by(AnalysisJob.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

    # 转换为带关联信息的response
    task_dict = schemas.SocialTaskRead.model_validate(task).model_dump()
    task_dict["monitor_name"] = task.monitor.name if task.monitor else None
    task_dict["platform_name"] = task.platform.name if task.platform else None
    task_dict["platform_code"] = task.platform.code if task.platform else None
    task_dict["creator_username"] = task.creator.username if task.creator else None
    task_dict["aggregation_status"] = aggregation_status
    return schemas.SocialTaskReadWithRelations(**task_dict)


@router.put(
    "/tasks/{task_id}",
    response_model=schemas.SocialTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Update task",
    description="更新任务信息",
)
async def update_task(
    task_update: schemas.SocialTaskUpdate,
    db: AsyncSession = Depends(get_async_db),
    task: SocialTask = Depends(validate_task_owner),
):
    """
    更新任务信息。

    只有任务创建者或项目owner可以更新任务。
    """
    updated_task = await service.update_task(db, task, task_update)
    return updated_task


@router.delete(
    "/tasks/{task_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete task",
    description="删除任务",
)
async def delete_task(
    db: AsyncSession = Depends(get_async_db),
    task: SocialTask = Depends(validate_task_owner),
):
    """
    删除任务（软删除）。

    只有任务创建者或项目owner可以删除任务。
    删除任务会级联软删除所有关联的原文和评论数据。
    """
    await service.delete_task(db, task)
    return MessageResponse(message=f"Task '{task.name}' deleted successfully")


@router.post(
    "/tasks/{task_id}/clear-data",
    response_model=schemas.SocialTaskRead,
    status_code=status.HTTP_200_OK,
    summary="Clear task data",
    description="清空任务的所有数据以便重新上传或采集",
)
async def clear_task_data(
    db: AsyncSession = Depends(get_async_db),
    task: SocialTask = Depends(validate_task_owner),
):
    """
    清空任务的所有数据（软删除原文和评论），重置任务状态。

    只有任务创建者或项目owner可以清空任务数据。
    清空后任务状态会重置为pending，可以重新上传或采集数据。
    """
    updated_task = await service.clear_task_data(db, task)
    return updated_task


# ==================== JSON Upload APIs ====================


@router.post(
    "/tasks/{task_id}/upload",
    response_model=schemas.JSONUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload JSON data",
    description="上传本地JSON数据到任务",
)
async def upload_json_data(
    task_id: int,
    upload_data: schemas.JSONUploadData,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传本地JSON数据到任务。

    要求：
    - 任务的data_source必须是'local_upload'
    - 任务状态必须是'pending'
    - 需要项目访问权限

    数据格式：
    ```json
    {
      "contents": [
        {
          "post_id_on_platform": "123456",
          "title": "标题",
          "content": "内容",
          ...
        }
      ],
      "comments": [
        {
          "comment_id_on_platform": "789",
          "content": "评论内容",
          "raw_data": {
            "post_id_on_platform": "123456"
          },
          ...
        }
      ]
    }
    ```
    """
    result = await service.process_json_upload(
        db, task_id=task_id, upload_data=upload_data, current_user_id=current_user.id
    )
    return schemas.JSONUploadResponse(**result)


# ==================== Data Query APIs ====================


@router.get(
    "/tasks/{task_id}/posts",
    response_model=schemas.SocialPostListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task posts",
    description="获取任务的原文列表",
)
async def get_task_posts(
    task_id: int,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    post_id: Optional[int] = Query(None, description="按原文ID精确筛选"),
):
    """
    获取任务的原文列表（分页）。

    需要项目访问权限。
    """
    posts, total = await service.get_task_posts(
        db,
        task_id=task_id,
        page=pagination.page,
        page_size=pagination.page_size,
        current_user_id=current_user.id,
        post_id=post_id,
    )

    # 转换为分页响应
    posts_read = [schemas.SocialPostRead.model_validate(p) for p in posts]
    return schemas.SocialPostListResponse.create(
        items=posts_read,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/tasks/{task_id}/comments",
    response_model=schemas.SocialCommentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task comments",
    description="获取任务的评论列表",
)
async def get_task_comments(
    task_id: int,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    post_id: Optional[int] = Query(None, description="按原文ID筛选评论"),
):
    """
    获取任务的评论列表（分页）。

    需要项目访问权限。
    评论按采集时间倒序排列。

    可选参数：
    - post_id: 筛选指定原文的评论
    """
    comments, total = await service.get_task_comments(
        db,
        task_id=task_id,
        page=pagination.page,
        page_size=pagination.page_size,
        current_user_id=current_user.id,
        post_id=post_id,
    )

    # 转换为分页响应
    comments_read = [schemas.SocialCommentRead.model_validate(c) for c in comments]
    return schemas.SocialCommentListResponse.create(
        items=comments_read,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/tasks/posts/{post_id}",
    response_model=schemas.SocialPostWithComments,
    status_code=status.HTTP_200_OK,
    summary="Get post with comments",
    description="获取原文及其评论",
)
async def get_post_with_comments(
    post_id: int,
    pagination: PaginationParams = Depends(get_pagination_params),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取原文及其评论列表。

    需要项目访问权限。
    评论按采集时间倒序排列。
    """
    post, comments, total = await service.get_post_with_comments(
        db,
        post_id=post_id,
        page=pagination.page,
        page_size=pagination.page_size,
        current_user_id=current_user.id,
    )

    # 构建响应
    post_dict = schemas.SocialPostRead.model_validate(post).model_dump()
    comments_list = [schemas.SocialCommentRead.model_validate(c) for c in comments]
    post_dict["comments"] = comments_list

    return schemas.SocialPostWithComments(**post_dict)


@router.get(
    "/tasks/posts/cross-task/{platform_id}/{post_id_on_platform}",
    response_model=schemas.PostQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query post across tasks",
    description="跨任务查询同一原文的历史数据",
)
async def query_cross_task_posts(
    platform_id: int,
    post_id_on_platform: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    monitor_id: Optional[int] = Query(None, description="限定项目范围"),
):
    """
    跨任务查询同一原文在不同任务中的数据。

    用途：查看同一原文在不同时间点的数据变化（赞评转数等）

    参数：
    - platform_id: 平台ID
    - post_id_on_platform: 平台上的原文ID
    - monitor_id: 可选，限定在某个项目范围内查询

    返回按采集时间倒序排列的所有记录。
    """
    posts = await service.query_cross_task_posts(
        db,
        platform_id=platform_id,
        post_id_on_platform=post_id_on_platform,
        monitor_id=monitor_id,
        current_user_id=current_user.id,
    )

    posts_read = [schemas.SocialPostRead.model_validate(p) for p in posts]

    # 统计任务数
    task_ids = set(p.task_id for p in posts)

    return schemas.PostQueryResponse(
        posts=posts_read,
        total_tasks=len(task_ids),
        message=f"Found {len(posts)} records across {len(task_ids)} tasks",
    )


# TODO: WebSocket爬虫通信端点（Stage 2.4实现）
# @router.websocket("/ws/crawler/{task_id}")
# async def websocket_crawler_endpoint(...):
#     """WebSocket端点，用于与爬虫平台通信"""
#     pass
