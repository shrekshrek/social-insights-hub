"""跨渠道 AnalysisJob 查询路由。

暴露以下端点（跨社媒/新闻/策略等所有渠道）：

- GET    /jobs                    全局分析任务列表
- GET    /jobs/{id}               任务详情
- GET    /jobs/{id}/progress      进度/成本
- POST   /jobs/{id}/cancel        取消
- DELETE /jobs/{id}               删除

路由本身不依赖任何渠道模块，所有业务逻辑在 src.jobs.crud。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.jobs import crud
from src.rbac.dependencies import (
    require_analysis_read,
    require_analysis_delete,
)
from src.jobs.schemas import (
    AnalysisJobListResponse,
    AnalysisJobResponse,
    AnalysisProgressResponse,
)

router = APIRouter(prefix="/jobs", tags=["Analysis Jobs"])


@router.get(
    "",
    response_model=AnalysisJobListResponse,
    summary="获取全局分析任务列表",
)
async def list_analysis_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    social_monitor_id: int | None = Query(None, description="按社媒监测项目ID筛选"),
    social_task_id: int | None = Query(None, description="按社媒采集任务ID筛选"),
    news_monitor_id: int | None = Query(None, description="按新闻监测项目ID筛选"),
    news_task_id: int | None = Query(None, description="按新闻采集任务ID筛选"),
    analysis_type: str | None = Query(None, description="按分析类型筛选"),
    status_filter: str | None = Query(None, alias="status", description="按状态筛选"),
    start_date: str | None = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="结束日期 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_analysis_read),
):
    """全局分析任务列表，支持按渠道/任务/类型/状态/日期筛选。"""
    items, total = await crud.get_analysis_jobs(
        db=db,
        current_user_id=current_user.id,
        page=page,
        page_size=page_size,
        social_monitor_id=social_monitor_id,
        social_task_id=social_task_id,
        news_monitor_id=news_monitor_id,
        news_task_id=news_task_id,
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
    "/{job_id}",
    response_model=AnalysisJobResponse,
    summary="获取分析任务详情",
)
async def get_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_analysis_read),
):
    result = await crud.get_analysis_job(db, job_id, current_user.id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found",
        )
    return AnalysisJobResponse.model_validate(result)


@router.get(
    "/{job_id}/progress",
    response_model=AnalysisProgressResponse,
    summary="获取分析任务进度",
)
async def get_analysis_progress(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_analysis_read),
):
    return await crud.get_analysis_progress(db, job_id, current_user.id)


@router.post(
    "/{job_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="取消分析任务",
)
async def cancel_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_analysis_read),
):
    success = await crud.cancel_analysis_job(db, job_id, current_user.id)
    return {"success": success, "message": "Analysis job cancelled"}


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_200_OK,
    summary="删除分析任务",
)
async def delete_analysis_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_analysis_delete),
):
    success = await crud.delete_analysis_job(db, job_id, current_user.id)
    return {"success": success, "message": "Analysis job deleted"}
