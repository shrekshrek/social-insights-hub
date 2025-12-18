"""分析模块API路由

API 结构：
- /jobs                          全局分析任务列表
- /jobs/{id}                     分析任务详情/删除
- /jobs/{id}/progress            进度查询
- /jobs/{id}/cancel              取消任务
- /tasks/{task_id}/screening     运行帖子初筛
- /tasks/{task_id}/deep-posts    运行帖子深度分析
- /tasks/{task_id}/deep-comments 运行评论深度分析
- /tasks/{task_id}/aggregation   POST运行聚合分析 / GET获取聚合结果
- /tasks/{task_id}/posts         帖子分析结果列表
- /tasks/{task_id}/preview       深度分析预览
- /projects/{project_id}/clustering   运行主题聚类（预留）
- /projects/{project_id}/competitive  运行竞品分析（预留）
- /stats                         全局统计
"""

from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db
from src.schemas import MessageResponse
from src.auth.dependencies import get_current_user
from src.auth.models import User

from . import service
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunClusteringRequest,
    RunCompetitiveRequest,
    RunAnalysisResponse,
    AnalysisJobResponse,
    AnalysisJobListResponse,
    AnalysisProgressResponse,
    AnalysisStatsResponse,
    PostAnalysisListResponse,
    PostAnalysisWithPostInfo,
    DeepAnalysisPreviewResponse,
    TaskAnalysisResultResponse,
    RunAggregationResponse,
    CreateProjectSnapshotRequest,
    ProjectSnapshotResponse,
    ProjectSnapshotListResponse,
)


router = APIRouter(
    prefix="/social-media/analysis",
    tags=["Social Media - Analysis"],
)


# ==================== 分析任务（全局资源）====================

@router.get(
    "/jobs",
    response_model=AnalysisJobListResponse,
    summary="获取全局分析任务列表",
)
async def get_analysis_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    project_id: int | None = Query(None, description="按项目ID筛选"),
    task_id: int | None = Query(None, description="按任务ID筛选"),
    analysis_type: str | None = Query(None, description="按分析类型筛选"),
    status_filter: str | None = Query(None, alias="status", description="按状态筛选"),
    start_date: str | None = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="结束日期 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取全局分析任务列表

    支持筛选条件：
    - project_id: 按项目筛选
    - task_id: 按数据任务筛选
    - analysis_type: screening_posts/deep_posts/deep_comments/topic_clustering/competitive
    - status: pending/processing/completed/failed
    - start_date/end_date: 日期范围
    """
    items, total = await service.get_analysis_jobs(
        db=db,
        current_user_id=current_user.id,
        page=page,
        page_size=page_size,
        project_id=project_id,
        task_id=task_id,
        analysis_type=analysis_type,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
    )

    return AnalysisJobListResponse(
        items=[AnalysisJobResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=AnalysisJobResponse,
    summary="获取分析任务详情",
)
async def get_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个分析任务详情"""
    result = await service.get_analysis_job(db, job_id, current_user.id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found",
        )

    return AnalysisJobResponse.model_validate(result)


@router.get(
    "/jobs/{job_id}/progress",
    response_model=AnalysisProgressResponse,
    summary="获取分析任务进度",
)
async def get_analysis_progress(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取分析任务进度

    - 实时查询任务状态和进度百分比
    - 显示当前Token使用和成本
    - 估算剩余处理时间
    """
    return await service.get_analysis_progress(db, job_id, current_user.id)


@router.post(
    "/jobs/{job_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="取消分析任务",
)
async def cancel_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消正在运行的分析任务

    - 仅可取消pending或processing状态的任务
    - 立即终止Celery任务执行
    """
    success = await service.cancel_analysis_job(db, job_id, current_user.id)
    return {"success": success, "message": "Analysis job cancelled"}


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="删除分析任务",
)
async def delete_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除分析任务记录"""
    success = await service.delete_analysis_job(db, job_id, current_user.id)
    return {"success": success, "message": "Analysis job deleted"}


# ==================== 任务级分析操作 ====================

@router.post(
    "/tasks/{task_id}/screening",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行帖子AI初筛分析",
)
async def run_post_screening(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行帖子AI初筛分析

    - 评估帖子的垃圾分、价值分、相关度和情感倾向
    - 分析该任务下所有未分析的帖子
    - 异步任务处理，返回任务ID用于查询进度
    """
    request = RunScreeningRequest(task_id=task_id, analyze_all=True)
    return await service.run_post_screening(db, request, current_user.id)


@router.post(
    "/tasks/{task_id}/deep-posts",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行帖子深度分析",
)
async def run_post_deep_analysis(
    task_id: int,
    spam_max: float | None = Query(None, ge=0, le=10, description="广告分上限"),
    value_min: float | None = Query(None, ge=0, le=10, description="价值分下限"),
    relevance_min: float | None = Query(None, ge=0, le=10, description="相关度分下限"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行帖子深度分析

    - 提取帖子的实体信息（品牌/商品/服务）
    - 提取通用观点
    - 生成内容总结
    - 支持阈值筛选
    """
    request = RunDeepAnalysisRequest(task_id=task_id)
    return await service.run_post_deep_analysis(
        db, request, current_user.id,
        spam_max=spam_max,
        value_min=value_min,
        relevance_min=relevance_min,
    )


@router.post(
    "/tasks/{task_id}/deep-comments",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行评论深度分析",
)
async def run_comment_deep_analysis(
    task_id: int,
    spam_max: float | None = Query(None, ge=0, le=10, description="广告分上限"),
    value_min: float | None = Query(None, ge=0, le=10, description="价值分下限"),
    relevance_min: float | None = Query(None, ge=0, le=10, description="相关度分下限"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行评论深度分析

    - 以帖子为单位，批量分析该帖子下的评论
    - 结合帖子的AI总结作为上下文
    - 提取评论中的实体信息和通用观点
    - 支持阈值筛选
    """
    request = RunDeepAnalysisRequest(task_id=task_id)
    return await service.run_comment_deep_analysis(
        db, request, current_user.id,
        spam_max=spam_max,
        value_min=value_min,
        relevance_min=relevance_min,
    )


@router.get(
    "/tasks/{task_id}/posts",
    response_model=PostAnalysisListResponse,
    summary="获取任务下帖子分析结果列表",
)
async def get_task_post_analyses(
    task_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    filter_analyzed: bool = Query(True, description="是否只返回已分析的帖子"),
    search_query: str | None = Query(None, description="关键词搜索（搜索标题和内容）"),
    search_id: int | None = Query(None, description="按帖子ID精确搜索"),
    post_ids: str | None = Query(None, description="按帖子ID列表筛选（逗号分隔）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取任务下所有帖子的分析结果

    - 返回该任务下已分析的帖子列表
    - 包含帖子基本信息和分析结果
    - 支持分页查询和搜索
    - 支持按帖子ID列表筛选（post_ids参数，逗号分隔）
    """
    # 解析 post_ids 参数
    post_ids_list: list[int] | None = None
    if post_ids:
        try:
            post_ids_list = [int(pid.strip()) for pid in post_ids.split(",") if pid.strip()]
        except ValueError:
            pass  # 忽略无效的ID

    items, total = await service.get_task_post_analyses(
        db, task_id, current_user.id, page, page_size, filter_analyzed,
        search_query=search_query, search_id=search_id, post_ids=post_ids_list
    )

    return PostAnalysisListResponse(
        items=[PostAnalysisWithPostInfo.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/tasks/{task_id}/aggregation",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="运行聚合分析",
)
async def run_task_aggregation(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行聚合分析，生成任务级分析报告（异步执行）

    - 基于已完成的初筛/深度分析数据，计算聚合指标
    - 生成 NSR、SERP、四象限、实体排行、IPA分析等
    - 任务异步执行，返回 job_id 用于查询进度
    - 结果存储在任务中，可通过 GET /aggregation 获取
    - 可多次调用，每次会覆盖之前的结果
    """
    return await service.run_task_aggregation(db, task_id, current_user.id)


@router.get(
    "/tasks/{task_id}/aggregation",
    response_model=TaskAnalysisResultResponse,
    summary="获取任务级聚合分析结果",
)
async def get_task_aggregation(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取任务级聚合分析结果

    - 返回 Aggregator 计算的聚合数据（NSR、SERP、四象限、实体、IPA等）
    - 需先调用 POST /aggregation 生成报告
    """
    result = await service.get_task_aggregation(db, task_id, current_user.id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analysis result found for this task. Please run aggregation first.",
        )

    return TaskAnalysisResultResponse.model_validate(result)


@router.get(
    "/tasks/{task_id}/preview",
    response_model=DeepAnalysisPreviewResponse,
    summary="获取深度分析预览",
)
async def preview_deep_analysis(
    task_id: int,
    spam_max: float | None = Query(None, ge=0, le=10, description="广告分上限"),
    value_min: float | None = Query(None, ge=0, le=10, description="价值分下限"),
    relevance_min: float | None = Query(None, ge=0, le=10, description="相关度分下限"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    基于初筛分阈值，预览可进行深度分析的帖子统计
    """
    preview = await service.preview_deep_analysis_candidates(
        db=db,
        task_id=task_id,
        current_user_id=current_user.id,
        spam_max=spam_max,
        value_min=value_min,
        relevance_min=relevance_min,
    )
    return DeepAnalysisPreviewResponse.model_validate(preview)


@router.delete(
    "/tasks/{task_id}/analyses",
    status_code=status.HTTP_200_OK,
    summary="删除任务下所有分析结果",
)
async def delete_task_analyses(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除任务下所有帖子的分析结果，方便重新分析

    - 会删除初筛结果（spam_score, value_score, relevance_score, sentiment）
    - 会删除帖子深度分析结果（post_deep_result）
    - 会删除评论深度分析结果（comment_deep_result）
    - 删除后可重新运行各类分析
    """
    result = await service.delete_task_analyses(db, task_id, current_user.id)
    return result


# ==================== 项目级分析操作（预留）====================

@router.post(
    "/projects/{project_id}/snapshots",
    response_model=ProjectSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="手动生成项目级合并分析快照",
)
async def create_project_snapshot(
    project_id: int,
    request: CreateProjectSnapshotRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """生成项目级合并分析快照，并自动启动项目级归一化与总结（异步）。

    - 创建快照：同步完成 Stage1 统计聚合（overview/details/charts/topic_aspects）
    - 自动启动：Stage2（全局归一化/归因增强）与 Stage3（整体总结）
    - 前端应轮询该快照详情，直至 stage2.status=completed 后再展示核心板块
    """
    snapshot = await service.create_project_snapshot(
        db=db,
        project_id=project_id,
        task_ids=request.task_ids,
        current_user_id=current_user.id,
        name=request.name,
    )

    # 创建后立刻启动异步增强（不需要额外接口）
    from datetime import datetime, timezone
    from src.social_media.analysis.celery_tasks.project_snapshot_tasks import enrich_project_snapshot_task

    now = datetime.now(timezone.utc).isoformat()
    result_data = snapshot.result_data or {}
    if not isinstance(result_data, dict):
        result_data = {}

    # 初始化流水线状态（供前端轮询展示）
    stage2 = {
        "status": "processing",
        "started_at": now,
        "updated_at": now,
        "steps": {
            "entity_normalization": {"status": "pending"},
            "opinion_normalization": {"status": "pending"},
            "derived_analysis": {"status": "pending"},
            "summary": {"status": "pending"},
        },
    }
    stage3 = {
        "status": "pending",
        "updated_at": now,
    }

    async_result = enrich_project_snapshot_task.delay(snapshot_id=snapshot.id)
    stage2["celery_task_id"] = str(async_result.id)
    result_data["stage2"] = stage2
    result_data["stage3"] = stage3
    snapshot.result_data = result_data
    await db.commit()
    await db.refresh(snapshot)
    return ProjectSnapshotResponse.model_validate(snapshot)


@router.get(
    "/projects/{project_id}/snapshots",
    response_model=ProjectSnapshotListResponse,
    summary="获取项目级合并分析快照列表",
)
async def list_project_snapshots(
    project_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目下的历史快照列表（按创建时间倒序）"""
    from src.social_media.projects import crud as project_crud
    from .models import ProjectAnalysisSnapshot
    from sqlalchemy import select

    has_access = await project_crud.check_project_access(db, project_id, current_user.id)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this project")

    stmt = (
        select(ProjectAnalysisSnapshot)
        .where(ProjectAnalysisSnapshot.project_id == project_id)
        .order_by(ProjectAnalysisSnapshot.created_at.desc())
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return ProjectSnapshotListResponse(items=[ProjectSnapshotResponse.model_validate(i) for i in items])


@router.get(
    "/projects/{project_id}/snapshots/{snapshot_id}",
    response_model=ProjectSnapshotResponse,
    summary="获取项目级合并分析快照详情",
)
async def get_project_snapshot(
    project_id: int,
    snapshot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个快照详情"""
    from src.social_media.projects import crud as project_crud
    from .models import ProjectAnalysisSnapshot
    from sqlalchemy import select

    has_access = await project_crud.check_project_access(db, project_id, current_user.id)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this project")

    stmt = (
        select(ProjectAnalysisSnapshot)
        .where(ProjectAnalysisSnapshot.id == snapshot_id)
        .where(ProjectAnalysisSnapshot.project_id == project_id)
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")
    return ProjectSnapshotResponse.model_validate(snapshot)


@router.delete(
    "/projects/{project_id}/snapshots/{snapshot_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除项目级合并分析快照",
)
async def delete_project_snapshot(
    project_id: int,
    snapshot_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除单个快照（硬删除）"""
    from src.social_media.projects import crud as project_crud
    from .models import ProjectAnalysisSnapshot
    from sqlalchemy import select

    has_access = await project_crud.check_project_access(db, project_id, current_user.id)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this project")

    stmt = (
        select(ProjectAnalysisSnapshot)
        .where(ProjectAnalysisSnapshot.id == snapshot_id)
        .where(ProjectAnalysisSnapshot.project_id == project_id)
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    await db.delete(snapshot)
    await db.commit()
    return MessageResponse(message=f"Snapshot {snapshot_id} deleted successfully")


@router.post(
    "/projects/{project_id}/clustering",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行主题聚类分析（预留）",
)
async def run_topic_clustering(
    project_id: int,
    request: RunClusteringRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行主题聚类分析（项目级）

    - 对项目下的帖子进行主题聚类
    - 支持指定源任务范围
    - 异步任务处理
    """
    # TODO: 实现主题聚类
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Topic clustering not implemented yet",
    )


@router.post(
    "/projects/{project_id}/competitive",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行竞品分析（预留）",
)
async def run_competitive_analysis(
    project_id: int,
    request: RunCompetitiveRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行竞品分析（项目级）

    - 对项目下的帖子进行竞品提及分析
    - 支持指定竞品关键词
    - 异步任务处理
    """
    # TODO: 实现竞品分析
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Competitive analysis not implemented yet",
    )


# ==================== 统计 ====================

@router.get(
    "/stats",
    response_model=AnalysisStatsResponse,
    summary="获取全局分析统计",
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


# ==================== 健康检查 ====================

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="分析服务健康检查",
)
async def health_check():
    """分析服务健康检查"""
    return {
        "status": "healthy",
        "service": "analysis",
        "message": "Analysis service is running",
    }
