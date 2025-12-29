"""Agent API 路由

提供爬虫客户端与平台通信的接口。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db
from .dependencies import verify_agent_api_key
from . import service
from .schemas import (
    PendingTasksResponse,
    AcceptTaskRequest,
    AcceptTaskResponse,
    ProgressUpdateRequest,
    ProgressUpdateResponse,
    UploadResultRequest,
    UploadResultResponse,
    HealthResponse,
)


router = APIRouter(
    prefix="/agent",
    tags=["Agent API"],
)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="检测平台服务是否可用（无需认证）",
)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/tasks/pending",
    response_model=PendingTasksResponse,
    status_code=status.HTTP_200_OK,
    summary="Get pending tasks",
    description="获取待执行任务列表",
    dependencies=[Depends(verify_agent_api_key)],
)
async def get_pending_tasks(
    db: AsyncSession = Depends(get_async_db),
    limit: int = Query(5, ge=1, le=20, description="最多返回任务数量"),
):
    """
    获取待执行任务列表。

    返回 `data_source=remote_crawler` 且 `status=pending` 的任务，
    按优先级降序、创建时间升序排列。
    """
    tasks = await service.get_pending_tasks(db, limit=limit)
    return PendingTasksResponse(tasks=tasks)


@router.post(
    "/tasks/{task_id}/accept",
    response_model=AcceptTaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept task",
    description="接收任务，防止重复执行",
    dependencies=[Depends(verify_agent_api_key)],
)
async def accept_task(
    task_id: int,
    request: AcceptTaskRequest = AcceptTaskRequest(),
    db: AsyncSession = Depends(get_async_db),
):
    """
    接收任务。

    调用后任务状态从 `pending` 变为 `accepted`。
    接口幂等，重复调用返回成功。
    """
    await service.accept_task(db, task_id, request)
    return AcceptTaskResponse(ok=True, message="任务已接收")


@router.post(
    "/tasks/{task_id}/progress",
    response_model=ProgressUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update progress",
    description="上报任务进度",
    dependencies=[Depends(verify_agent_api_key)],
)
async def update_progress(
    task_id: int,
    request: ProgressUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    上报任务进度。

    建议每 30 秒或每处理 10 条数据上报一次。
    进度上报失败不应中断任务执行。
    """
    await service.update_progress(db, task_id, request)
    return ProgressUpdateResponse(ok=True)


@router.post(
    "/tasks/{task_id}/result",
    response_model=UploadResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload result",
    description="上传任务结果",
    dependencies=[Depends(verify_agent_api_key)],
)
async def upload_result(
    task_id: int,
    request: UploadResultRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    上传任务结果。

    请求体建议使用 gzip 压缩以节省带宽。
    上传成功后任务状态变为 `completed`。
    """
    stored = await service.upload_result(db, task_id, request)
    return UploadResultResponse(ok=True, stored=stored)
