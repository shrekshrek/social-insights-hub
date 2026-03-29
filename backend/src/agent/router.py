"""Agent API 路由

提供爬虫客户端与平台通信的接口。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db
from .dependencies import verify_agent_api_key
from . import service
from .schemas import (
    AgentTaskInfo,
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

    返回 `data_source=remote_crawler` 且 `status in (pending, approved)` 的任务，
    按优先级降序、创建时间升序排列。
    pending = 新任务（需 accept），approved = 续采任务（跳过 accept 直接执行）。
    """
    tasks = await service.get_pending_tasks(db, limit=limit)
    return PendingTasksResponse(tasks=tasks)


@router.get(
    "/tasks/{task_id}",
    response_model=AgentTaskInfo,
    status_code=status.HTTP_200_OK,
    summary="Get task detail",
    description="查询任务详情（状态、参数），供爬虫轮询执行状态",
    dependencies=[Depends(verify_agent_api_key)],
)
async def get_task_detail(
    task_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """查询指定任务的详细信息，包含 task_params。"""
    return await service.get_task_detail(db, task_id)


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
    错误响应使用扁平 JSON（非 FastAPI 默认的 detail 包装），供爬虫客户端直接解析。
    """
    try:
        await service.accept_task(db, task_id, request)
        return AcceptTaskResponse(ok=True, message="任务已接收")
    except HTTPException as e:
        # 返回扁平 JSON（爬虫客户端解析 ok/error_code 字段，不兼容 FastAPI 默认的 {"detail": ...} 包装）
        content = e.detail if isinstance(e.detail, dict) else {"ok": False, "message": str(e.detail)}
        return JSONResponse(status_code=e.status_code, content=content)


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
    上传成功后任务状态变为 `completed`（或 `probe_ready`）；
    携带 `error_message` 时任务状态变为 `failed`（仍保留已采集数据）。
    错误响应使用扁平 JSON，供爬虫客户端直接解析。
    """
    try:
        stored = await service.upload_result(db, task_id, request)
        return UploadResultResponse(ok=True, stored=stored)
    except HTTPException as e:
        content = e.detail if isinstance(e.detail, dict) else {"ok": False, "message": str(e.detail)}
        return JSONResponse(status_code=e.status_code, content=content)
