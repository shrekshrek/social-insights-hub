"""新闻任务 API 路由"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.database import get_async_db
from src.rbac.dependencies import (
    require_news_task_read,
    require_news_task_write,
    require_news_task_delete,
)
from src.news_media.monitors.dependencies import validate_news_monitor_exists
from src.news_media.monitors.models import NewsMonitor
from src.news_media.tasks import service
from src.news_media.tasks.dependencies import validate_news_task_access
from src.news_media.tasks.models import NewsTask
from src.news_media.tasks.schemas import (
    ChannelCount,
    NewsArticleRead,
    NewsTaskChannelStats,
    NewsTaskCreate,
    NewsTaskRead,
    NewsTaskReadWithRelations,
)
from src.schemas import MessageResponse, PaginatedResponse

router = APIRouter(prefix="/news-media", tags=["News Media - Tasks"])


# ==================== Task Endpoints ====================


@router.get(
    "/tasks",
    response_model=PaginatedResponse[NewsTaskReadWithRelations],
    status_code=status.HTTP_200_OK,
    summary="获取所有新闻任务（跨项目）",
)
async def list_all_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status_filter: Literal["pending", "running", "completed", "failed"] | None = Query(default=None, alias="status"),
    phase: Literal["probe", "collect"] | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_task_read),
):
    tasks, total = await service.get_news_tasks(
        db, page=page, page_size=page_size,
        status_filter=status_filter, phase=phase, search=search,
    )
    items = [NewsTaskReadWithRelations.from_orm_full(t) for t in tasks]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


async def _dispatch_news_collect_task(
    task: NewsTask,
    db: AsyncSession,
    user_id: int,
) -> NewsTask:
    """派发新闻全量采集 Celery 任务（create 时自动调用 + execute 手动重试共用此 helper）

    假设 caller 已完成业务校验（phase != probe / strategy_id is None / status 允许执行）。
    职责：切换任务状态 → 按需创建 tagging job → 派发 celery → 回写 celery_task_id。
    """
    from src.jobs import crud as jobs_crud
    from src.news_media.analysis.jobs import create_news_tagging_job
    from src.news_media.tasks.tasks import run_news_collect_task

    task.status = "running"
    task.error_message = None
    await db.commit()
    await db.refresh(task)

    tagging_job_id: int | None = None
    if task.auto_analyze:
        tagging_job = await create_news_tagging_job(db=db, task=task, user_id=user_id)
        tagging_job_id = tagging_job.id
        await db.commit()

    celery_result = run_news_collect_task.delay(
        task_id=task.id,
        tagging_job_id=tagging_job_id,
    )

    if tagging_job_id is not None:
        await jobs_crud.set_celery_task_id(db, tagging_job_id, celery_result.id)
        await db.commit()

    return task


@router.post(
    "/monitors/{monitor_id}/tasks",
    response_model=NewsTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建新闻任务（独立 monitor 场景自动派发执行）",
)
async def create_task(
    data: NewsTaskCreate,
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_news_task_write),
):
    """独立 monitor 场景：创建后立即自动派发执行（对齐社媒 Pull 模式的 UX，用户无需二次点击）。

    仅 phase != "probe" 的独立任务（strategy_id is None）会自动派发；probe 任务仍由
    strategies 模块编排（走 strategies/service.py 的批量端点），此处不自动触发。
    """
    task = await service.create_news_task(db, monitor.id, data, current_user.id, phase=data.phase)

    if task.strategy_id is None and task.phase != "probe":
        task = await _dispatch_news_collect_task(task, db, current_user.id)

    return task


@router.get(
    "/monitors/{monitor_id}/tasks",
    response_model=PaginatedResponse[NewsTaskReadWithRelations],
    status_code=status.HTTP_200_OK,
    summary="获取监测项目的任务列表",
)
async def list_monitor_tasks(
    monitor: NewsMonitor = Depends(validate_news_monitor_exists),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status_filter: Literal["pending", "running", "completed", "failed"] | None = Query(default=None, alias="status"),
    phase: Literal["probe", "collect"] | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_task_read),
):
    tasks, total = await service.get_news_tasks(
        db, page=page, page_size=page_size,
        monitor_id=monitor.id, status_filter=status_filter,
        phase=phase, search=search,
    )
    items = [NewsTaskReadWithRelations.from_orm_full(t) for t in tasks]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/tasks/{task_id}",
    response_model=NewsTaskReadWithRelations,
    status_code=status.HTTP_200_OK,
    summary="获取新闻任务详情",
)
async def get_task(
    task: NewsTask = Depends(validate_news_task_access),
    _: User = Depends(require_news_task_read),
):
    return NewsTaskReadWithRelations.from_orm_full(task)


@router.delete(
    "/tasks/{task_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除新闻任务",
)
async def delete_task(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    _: User = Depends(require_news_task_delete),
):
    await service.delete_news_task(db, task)
    return MessageResponse(message=f"任务 '{task.name}' 已删除")


@router.post(
    "/tasks/{task_id}/execute",
    response_model=NewsTaskRead,
    status_code=status.HTTP_200_OK,
    summary="执行新闻任务（手动重试/重跑入口）",
)
async def execute_task(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_news_task_write),
):
    """手动执行入口：主要用于 **失败重试** 或 **历史 pending 任务重跑**。

    正常流程中，独立 monitor 任务在 create 时已自动派发（见 create_task），用户无需调用本端点。
    独立场景不走 probe/collect 两段式 —— probe 只在 strategy 研究流程里用，由 strategies 模块
    内部派发，本端点拒绝。
    """
    from fastapi import HTTPException

    if task.strategy_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略任务请通过策略端点执行",
        )
    if task.phase == "probe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="独立场景不支持 probe 任务，请创建 collect 任务",
        )
    if task.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务当前状态为 {task.status}，无法执行",
        )

    return await _dispatch_news_collect_task(task, db, current_user.id)


# ==================== Article Endpoints ====================


@router.get(
    "/tasks/{task_id}/articles",
    response_model=PaginatedResponse[NewsArticleRead],
    status_code=status.HTTP_200_OK,
    summary="获取任务的文章列表",
)
async def list_task_articles(
    task: NewsTask = Depends(validate_news_task_access),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    relevance: Literal["high", "medium", "low"] | None = Query(default=None),
    source_tier: Literal["tier1", "tier2", "tier3", "wechat_mp"] | None = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_task_read),
):
    from src.news_media.tasks import crud as tasks_crud

    skip = (page - 1) * page_size
    articles, total = await tasks_crud.get_articles_by_task(
        db, task_id=task.id, skip=skip, limit=page_size,
        relevance=relevance, source_tier=source_tier,
    )
    items = [NewsArticleRead.model_validate(a) for a in articles]
    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/tasks/{task_id}/channel-stats",
    response_model=NewsTaskChannelStats,
    status_code=status.HTTP_200_OK,
    summary="获取任务的渠道采集量分布（原始召回 vs 去重入库）",
)
async def get_task_channel_stats(
    task: NewsTask = Depends(validate_news_task_access),
    db: AsyncSession = Depends(get_async_db),
    _current_user: User = Depends(require_news_task_read),
):
    """返回各搜索渠道的两个数字：
    - raw: 该渠道去重前的原始召回量（从 task.analysis_result.meta.channel_raw_counts 读）
    - deduped: 该渠道在 URL 跨渠道去重后实际入库的文章数（实时 SQL group by）

    任务尚未完成、或采集前创建的旧任务（无 channel_raw_counts），raw 字段为 0。
    """
    from src.news_media.tasks import crud as tasks_crud

    deduped_counts = await tasks_crud.get_channel_stats_by_task(db, task.id)
    meta = (task.analysis_result or {}).get("meta", {})
    raw_counts: dict = meta.get("channel_raw_counts") or {}

    def _count(ch: str) -> ChannelCount:
        return ChannelCount(
            raw=int(raw_counts.get(ch, 0)),
            deduped=deduped_counts.get(ch, 0),
        )

    return NewsTaskChannelStats(
        baidu=_count("baidu"),
        sogou=_count("sogou"),
        bing=_count("bing"),
        wechat_mp=_count("wechat_mp"),
        raw_total=sum(int(v) for v in raw_counts.values()),
        deduped_total=sum(deduped_counts.values()),
    )
