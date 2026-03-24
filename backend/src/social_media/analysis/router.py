"""分析模块API路由

API 结构：
- /jobs                          全局分析任务列表
- /jobs/{id}                     分析任务详情/删除
- /jobs/{id}/progress            进度查询
- /jobs/{id}/cancel              取消任务
- /tasks/{task_id}/screening     运行原文初筛
- /tasks/{task_id}/deep-posts    运行原文深度分析
- /tasks/{task_id}/deep-comments 运行评论深度分析
- /tasks/{task_id}/aggregation   POST运行聚合分析 / GET获取聚合结果
- /tasks/{task_id}/posts         原文分析结果列表
- /tasks/{task_id}/preview       深度分析预览
- /monitors/{monitor_id}/slices  项目级切片 CRUD
- /stats                         全局统计
"""

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, status, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.database import get_async_db
from src.schemas import MessageResponse
from src.auth.dependencies import get_current_user
from src.auth.models import User

from . import service
from .schemas import (
    RunScreeningRequest,
    RunDeepAnalysisRequest,
    RunAnalysisResponse,
    AnalysisJobResponse,
    AnalysisJobListResponse,
    AnalysisProgressResponse,
    AnalysisStatsResponse,
    PostAnalysisListResponse,
    PostAnalysisWithPostInfo,
    DeepAnalysisPreviewResponse,
    TaskAnalysisResultResponse,
    CreateProjectSliceRequest,
    ProjectSliceResponse,
    ProjectSliceListResponse,
    UpdateProjectSliceRequest,
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
    monitor_id: int | None = Query(None, description="按项目ID筛选"),
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
    - monitor_id: 按项目筛选
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
        monitor_id=monitor_id,
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
    summary="运行原文AI初筛分析",
)
async def run_post_screening(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    运行原文AI初筛分析

    - 评估原文的垃圾分、价值分、相关度和情感倾向
    - 分析该任务下所有未分析的原文
    - 异步任务处理，返回任务ID用于查询进度
    """
    request = RunScreeningRequest(task_id=task_id, analyze_all=True)
    return await service.run_post_screening(db, request, current_user.id)


@router.post(
    "/tasks/{task_id}/deep-posts",
    response_model=RunAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="运行原文深度分析",
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
    运行原文深度分析

    - 提取原文的实体信息（品牌/商品/服务）
    - 提取通用观点
    - 生成内容总结
    - 支持阈值筛选
    """
    request = RunDeepAnalysisRequest(task_id=task_id)
    return await service.run_post_deep_analysis(
        db,
        request,
        current_user.id,
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

    - 以原文为单位，批量分析该原文下的评论
    - 结合原文的AI总结作为上下文
    - 提取评论中的实体信息和通用观点
    - 支持阈值筛选
    """
    request = RunDeepAnalysisRequest(task_id=task_id)
    return await service.run_comment_deep_analysis(
        db,
        request,
        current_user.id,
        spam_max=spam_max,
        value_min=value_min,
        relevance_min=relevance_min,
    )


@router.get(
    "/tasks/{task_id}/posts",
    response_model=PostAnalysisListResponse,
    summary="获取任务下原文分析结果列表",
)
async def get_task_post_analyses(
    task_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    filter_analyzed: bool = Query(True, description="是否只返回已分析的原文"),
    search_query: str | None = Query(None, description="关键词搜索（搜索标题和内容）"),
    search_id: int | None = Query(None, description="按原文ID精确搜索（对应表格ID列）"),
    post_ids: str | None = Query(None, description="按原文ID列表筛选（逗号分隔）"),
    spam_group: str | None = Query(None, description="按垃圾分组筛选（high=推广/low=有机）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取任务下所有原文的分析结果

    - 返回该任务下已分析的原文列表
    - 包含原文基本信息和分析结果
    - 支持分页查询和搜索
    - 支持按原文ID列表筛选（post_ids参数，逗号分隔）
    - 支持按垃圾分组筛选（spam_group=high/low）
    """
    # 解析 post_ids 参数
    post_ids_list: list[int] | None = None
    if post_ids:
        try:
            post_ids_list = [
                int(pid.strip()) for pid in post_ids.split(",") if pid.strip()
            ]
        except ValueError:
            pass  # 忽略无效的ID

    # 校验 spam_group 参数
    valid_spam_group = spam_group if spam_group in ("high", "low") else None

    items, total = await service.get_task_post_analyses(
        db,
        task_id,
        current_user.id,
        page,
        page_size,
        filter_analyzed,
        search_query=search_query,
        search_id=search_id,
        post_ids=post_ids_list,
        spam_group=valid_spam_group,
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
    基于初筛分阈值，预览可进行深度分析的原文统计
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
    删除任务下所有原文的分析结果，方便重新分析

    - 会删除初筛结果（spam_score, value_score, relevance_score, sentiment）
    - 会删除原文深度分析结果（post_deep_result）
    - 会删除评论深度分析结果（comment_deep_result）
    - 删除后可重新运行各类分析
    """
    result = await service.delete_task_analyses(db, task_id, current_user.id)
    return result


# ==================== 项目级切片操作 ====================


@router.post(
    "/monitors/{monitor_id}/slices",
    response_model=ProjectSliceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="手动生成项目级合并分析切片",
)
async def create_monitor_slice(
    monitor_id: int,
    request: CreateProjectSliceRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """生成项目级合并分析切片，并自动启动项目级归一化与总结（异步）。

    - 创建切片：同步完成 Stage1 统计聚合（overview/details/charts/topic_aspects）
    - 自动启动：Stage2（全局归一化/归因增强）与 Stage3（整体总结）
    - 前端应轮询该切片详情，直至 pipeline.stage2.status=completed 后再展示核心板块
    """
    slice_record = await service.create_monitor_slice(
        db=db,
        monitor_id=monitor_id,
        task_ids=request.task_ids,
        current_user_id=current_user.id,
        name=request.name,
        subject=request.subject,
        competitors=request.competitors,
        platform_weights=request.platform_weights,
    )

    # 创建后立刻启动异步增强（不需要额外接口）
    from datetime import datetime, timezone
    from src.social_media.analysis.celery_tasks.monitor_slice_tasks import (
        run_monitor_slice_task,
    )

    now = datetime.now(timezone.utc).isoformat()
    # 重要：result_data 是 JSON 字段，直接原地修改可能不会被 SQLAlchemy 追踪到（导致不落库）
    result_data = slice_record.result_data or {}
    if not isinstance(result_data, dict):
        result_data = {}
    # 触发变更追踪：用新 dict 承载本次更新
    result_data = dict(result_data)

    # 初始化流水线状态（供前端轮询展示）
    async_result = run_monitor_slice_task.delay(slice_id=slice_record.id)
    result_data["pipeline"] = {
        "stage2": {
            "status": "processing",
            "started_at": now,
            "updated_at": now,
            "celery_task_id": str(async_result.id),
            "steps": {
                "entity_normalization": {"status": "pending"},
                "opinion_normalization": {"status": "pending"},
                "derived_analysis": {"status": "pending"},
            },
        },
        "stage3": {
            "status": "pending",
            "updated_at": now,
        },
    }
    slice_record.result_data = result_data
    flag_modified(slice_record, "result_data")
    await db.commit()
    await db.refresh(slice_record)
    return ProjectSliceResponse.model_validate(slice_record)


@router.get(
    "/monitors/{monitor_id}/slices",
    response_model=ProjectSliceListResponse,
    summary="获取项目级合并分析切片列表",
)
async def list_monitor_slices(
    monitor_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目下的历史切片列表（按创建时间倒序）"""
    from src.social_media.monitors import crud as monitor_crud
    from .models import AnalysisSlice
    from sqlalchemy import select

    has_access = await monitor_crud.check_monitor_access(
        db, monitor_id, current_user.id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this monitor",
        )

    stmt = (
        select(AnalysisSlice)
        .where(AnalysisSlice.monitor_id == monitor_id)
        .order_by(AnalysisSlice.created_at.desc())
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return ProjectSliceListResponse(
        items=[ProjectSliceResponse.model_validate(i) for i in items]
    )


@router.get(
    "/monitors/{monitor_id}/slices/{slice_id}",
    response_model=ProjectSliceResponse,
    summary="获取项目级合并分析切片详情",
)
async def get_monitor_slice(
    monitor_id: int,
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个切片详情"""
    from src.social_media.monitors import crud as monitor_crud
    from .models import AnalysisSlice
    from sqlalchemy import select

    has_access = await monitor_crud.check_monitor_access(
        db, monitor_id, current_user.id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this monitor",
        )

    stmt = (
        select(AnalysisSlice)
        .where(AnalysisSlice.id == slice_id)
        .where(AnalysisSlice.monitor_id == monitor_id)
    )
    result = await db.execute(stmt)
    slice_record = result.scalar_one_or_none()
    if not slice_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Slice not found"
        )
    return ProjectSliceResponse.model_validate(slice_record)


@router.patch(
    "/monitors/{monitor_id}/slices/{slice_id}",
    response_model=ProjectSliceResponse,
    status_code=status.HTTP_200_OK,
    summary="更新切片名称",
    description="重命名项目级合并分析切片",
    tags=["Social Media - Analysis"],
)
async def update_monitor_slice(
    monitor_id: int,
    slice_id: int,
    request: UpdateProjectSliceRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """更新切片名称。需要项目访问权限。"""
    from src.social_media.monitors import crud as monitor_crud
    from .models import AnalysisSlice
    from sqlalchemy import select

    has_access = await monitor_crud.check_monitor_access(
        db, monitor_id, current_user.id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this monitor",
        )

    stmt = (
        select(AnalysisSlice)
        .where(AnalysisSlice.id == slice_id)
        .where(AnalysisSlice.monitor_id == monitor_id)
    )
    result = await db.execute(stmt)
    slice_record = result.scalar_one_or_none()
    if not slice_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Slice not found"
        )

    slice_record.name = request.name
    await db.commit()
    await db.refresh(slice_record)
    return ProjectSliceResponse.model_validate(slice_record)


@router.delete(
    "/monitors/{monitor_id}/slices/{slice_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除项目级合并分析切片",
)
async def delete_monitor_slice(
    monitor_id: int,
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除单个切片（硬删除）"""
    from src.social_media.monitors import crud as monitor_crud
    from .models import AnalysisSlice
    from sqlalchemy import select

    has_access = await monitor_crud.check_monitor_access(
        db, monitor_id, current_user.id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this monitor",
        )

    stmt = (
        select(AnalysisSlice)
        .where(AnalysisSlice.id == slice_id)
        .where(AnalysisSlice.monitor_id == monitor_id)
    )
    result = await db.execute(stmt)
    slice_record = result.scalar_one_or_none()
    if not slice_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Slice not found"
        )

    await db.delete(slice_record)
    await db.commit()
    return MessageResponse(message=f"Slice {slice_id} deleted successfully")


# ==================== 切片导出 ====================


@router.get(
    "/monitors/{monitor_id}/slices/{slice_id}/export",
    status_code=status.HTTP_200_OK,
    summary="导出切片报告为 Word 文档",
    tags=["Social Media - Analysis"],
)
async def export_monitor_slice(
    monitor_id: int,
    slice_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """导出切片的 AI 报告为 Word (.docx) 文档。

    包含封面、概览摘要和已完成的报告（行业格局、话题洞察、战略诊断）。
    """
    from src.social_media.monitors import crud as monitor_crud
    from .models import AnalysisSlice
    from .export_docx import generate_slice_report_docx

    has_access = await monitor_crud.check_monitor_access(
        db, monitor_id, current_user.id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this monitor",
        )

    stmt = (
        select(AnalysisSlice)
        .where(AnalysisSlice.id == slice_id)
        .where(AnalysisSlice.monitor_id == monitor_id)
    )
    result = await db.execute(stmt)
    slice_record = result.scalar_one_or_none()
    if not slice_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Slice not found"
        )

    reports = (slice_record.result_data or {}).get("reports")
    if not reports:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该切片尚未生成报告，无法导出",
        )

    buf: BytesIO = generate_slice_report_docx(slice_record)

    monitor_name = (
        slice_record.monitor.name if slice_record.monitor else "report"
    )
    slice_name = slice_record.name or f"slice_{slice_id}"
    filename = f"{monitor_name}_{slice_name}.docx"
    encoded_filename = quote(filename)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{encoded_filename}"
            ),
        },
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
