"""分析模块API路由"""

from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.rbac.dependencies import create_permission_dependency

# 创建分析模块的权限依赖
require_run_screening = create_permission_dependency("analysis:task.run_screening")
require_run_deep = create_permission_dependency("analysis:task.run_deep")
require_view_results = create_permission_dependency("analysis:task.view_results")
require_delete_results = create_permission_dependency("analysis:task.delete_results")
require_view_stats = create_permission_dependency("analysis:stats.view")

from . import service
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunClusteringRequest,
    RunCompetitiveRequest,
    RunAnalysisResponse,
    TaskAnalysisResultResponse,
    TaskAnalysisResultListResponse,
    AnalysisProgressResponse,
    AnalysisStatsResponse,
    PostAnalysisResponse,
    CommentAnalysisResponse,
)
from .models import TaskAnalysisResult, PostAnalysis, CommentAnalysis


router = APIRouter(
    prefix="/social-media/analysis",
    tags=["Analysis"],
)


# ==================== 任务级分析 ====================

@router.post(
    "/tasks/screening/posts",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行帖子AI初筛分析",
    dependencies=[Depends(require_run_screening)],
)
async def run_post_screening(
    request: RunScreeningRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行帖子AI初筛分析

    - 评估帖子的垃圾分、价值分、相关度和情感倾向
    - 支持批量分析或分析所有帖子
    - 异步任务处理，返回任务ID用于查询进度
    """
    return await service.run_post_screening(db, request, current_user.id)


@router.post(
    "/tasks/screening/comments",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行评论AI初筛分析",
    dependencies=[Depends(require_run_screening)],
)
async def run_comment_screening(
    request: RunScreeningRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行评论AI初筛分析

    - 评估评论的垃圾分、价值分、相关度和情感倾向
    - 支持批量分析或分析所有评论
    - 异步任务处理
    """
    return await service.run_comment_screening(db, request, current_user.id)


@router.get(
    "/tasks/{task_id}/results",
    response_model=TaskAnalysisResultListResponse,
    summary="获取任务的分析结果列表",
    dependencies=[Depends(require_view_results)],
)
async def get_task_analysis_results(
    task_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取任务的分析结果列表

    - 分页查询指定任务的所有分析结果
    - 包含初筛和深度分析的所有记录
    """
    items, total = await service.get_task_analysis_results(
        db, task_id, current_user.id, page, page_size
    )

    return TaskAnalysisResultListResponse(
        items=[TaskAnalysisResultResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/tasks/results/{result_id}",
    response_model=TaskAnalysisResultResponse,
    summary="获取分析结果详情",
    dependencies=[Depends(require_view_results)],
)
async def get_task_analysis_result(
    result_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个任务分析结果详情

    - 包含完整的分析数据和Token使用统计
    - 显示任务状态、进度和成本信息
    """
    result = await service.get_task_analysis_result(db, result_id, current_user.id)

    if not result:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis result not found",
        )

    return TaskAnalysisResultResponse.model_validate(result)


@router.get(
    "/tasks/results/{result_id}/progress",
    response_model=AnalysisProgressResponse,
    summary="获取分析任务进度",
    dependencies=[Depends(require_view_results)],
)
async def get_analysis_progress(
    result_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取分析任务进度

    - 实时查询任务状态和进度百分比
    - 显示当前Token使用和成本
    - 估算剩余处理时间
    """
    return await service.get_analysis_progress(db, result_id, current_user.id)


@router.post(
    "/tasks/results/{result_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="取消分析任务",
    dependencies=[Depends(require_run_screening)],
)
async def cancel_analysis(
    result_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消正在运行的分析任务

    - 仅可取消pending或processing状态的任务
    - 立即终止Celery任务执行
    """
    success = await service.cancel_analysis(db, result_id, current_user.id)
    return {"success": success, "message": "Analysis task cancelled"}


@router.delete(
    "/tasks/results/{result_id}",
    status_code=status.HTTP_200_OK,
    summary="删除分析结果",
    dependencies=[Depends(require_delete_results)],
)
async def delete_analysis_result(
    result_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除分析结果记录

    - 删除任务分析结果及相关数据
    - 不影响原始帖子和评论数据
    """
    success = await service.delete_analysis_result(db, result_id, current_user.id)
    return {"success": success, "message": "Analysis result deleted"}


# ==================== 统计和查询 ====================

@router.get(
    "/stats/global",
    response_model=AnalysisStatsResponse,
    summary="获取全局分析统计",
    dependencies=[Depends(require_view_stats)],
)
async def get_global_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取全局分析统计

    - 显示总任务数、完成数、失败数等
    - 统计总Token使用量和成本
    - 计算平均处理时间
    """
    return await service.get_global_stats(db, current_user.id)


@router.get(
    "/posts/{post_id}",
    response_model=PostAnalysisResponse,
    summary="获取帖子的分析结果",
    dependencies=[Depends(require_view_results)],
)
async def get_post_analysis(
    post_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个帖子的分析结果

    - 返回帖子的初筛评分和深度分析内容
    - 如果尚未分析则返回404
    """
    result = await service.get_post_analysis(db, post_id, current_user.id)

    if not result:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post analysis not found",
        )

    return PostAnalysisResponse.model_validate(result)


@router.get(
    "/comments/{comment_id}",
    response_model=CommentAnalysisResponse,
    summary="获取评论的分析结果",
    dependencies=[Depends(require_view_results)],
)
async def get_comment_analysis(
    comment_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个评论的分析结果

    - 返回评论的初筛评分和深度分析内容
    - 如果尚未分析则返回404
    """
    result = await service.get_comment_analysis(db, comment_id, current_user.id)

    if not result:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment analysis not found",
        )

    return CommentAnalysisResponse.model_validate(result)


# ==================== 健康检查 ====================

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="分析服务健康检查",
)
async def health_check():
    """
    分析服务健康检查

    - 验证服务是否正常运行
    - 检查Celery连接状态
    """
    return {
        "status": "healthy",
        "service": "analysis",
        "message": "Analysis service is running",
    }
