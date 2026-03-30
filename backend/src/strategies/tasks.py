"""策略后台任务（Celery/Beat 调度）

主动检测策略状态，替代原有「前端轮询才能触发」的设计缺陷：
- auto_probe_review_task:    探测任务全部分析完成 → 自动触发 LLM 审查
- auto_collection_check_task: 全量采集全部完成   → 自动触发建切片 + 覆盖度验证
"""

import asyncio
import logging

from sqlalchemy import and_, select

from src.celery_app import celery_app
from src.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def _check_probing_strategies() -> int:
    """找出所有探测完成但尚未触发审查的策略，触发 LLM 审查。

    1. 查询 status=probing 且 probe_review_result=None 的策略
    2. 确认所有 probe 任务均已完成分析
    3. 调用 _run_probe_review_bg_task（内部自开 session，与本函数 session 无冲突）
    """
    from src.strategies.models import Strategy
    from src.strategies.service import (
        _build_probe_task_summaries,
        _probe_review_in_progress,
        _run_probe_review_bg_task,
    )

    to_review: list[tuple[int, list[dict]]] = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.status == "probing")
        )
        strategies = result.scalars().all()

        for strategy in strategies:
            if strategy.probe_review_result is not None:
                continue
            if strategy.id in _probe_review_in_progress:
                continue
            task_ids = list(strategy.task_ids or [])
            if not task_ids:
                continue

            task_statuses, analyzed_summaries = await _build_probe_task_summaries(
                db, task_ids
            )
            all_analyzed = bool(task_statuses) and all(
                t.has_analysis for t in task_statuses
            )
            if all_analyzed:
                to_review.append((strategy.id, analyzed_summaries))

    # 在 session 关闭后调用，_run_probe_review_bg_task 内部自开 session
    for strategy_id, analyzed_summaries in to_review:
        if strategy_id not in _probe_review_in_progress:
            _probe_review_in_progress.add(strategy_id)
            await _run_probe_review_bg_task(strategy_id, analyzed_summaries)
            logger.info("Strategy %d: probe review triggered by Beat task", strategy_id)

    return len(to_review)


async def _check_collecting_strategies() -> int:
    """找出全量采集完成但尚未建切片的策略，触发自动建切片 + 覆盖度验证。

    1. 查询 status=collecting 且无 StrategySlice 的策略
    2. 确认所有 collect 任务均 completed 且已有分析结果
    3. 调用 _create_auto_slices（内部 commit，不需要外层提交）
    """
    from src.social_media.tasks.models import DataTask
    from src.strategies.models import Strategy, StrategySlice
    from src.strategies.service import _create_auto_slices, get_strategy_by_id

    triggered = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.status == "collecting")
        )
        strategies = result.scalars().all()

        for strategy in strategies:
            task_ids = list(strategy.task_ids or [])
            if not task_ids:
                continue

            tasks_result = await db.execute(
                select(DataTask).where(
                    and_(
                        DataTask.id.in_(task_ids),
                        DataTask.phase == "collect",
                        DataTask.is_deleted.is_(False),
                    )
                )
            )
            tasks = list(tasks_result.scalars().all())
            if not tasks:
                continue

            if not all(t.status == "completed" for t in tasks):
                continue
            if not all(t.analysis_result is not None for t in tasks):
                continue

            # 已有切片则跳过（幂等保护）
            existing = await db.execute(
                select(StrategySlice)
                .where(StrategySlice.strategy_id == strategy.id)
                .limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            try:
                full_strategy = await get_strategy_by_id(db, strategy.id)
                await _create_auto_slices(
                    db, full_strategy, tasks, current_user_id=strategy.created_by
                )
                triggered += 1
                logger.info(
                    "Strategy %d: slices auto-created by Beat task", strategy.id
                )
            except Exception as e:
                logger.error(
                    "Strategy %d: auto-slice creation failed: %s",
                    strategy.id,
                    e,
                    exc_info=True,
                )

    return triggered


@celery_app.task(name="strategies.auto_probe_review", bind=True, max_retries=0)
def auto_probe_review_task(self) -> dict:
    """Beat 触发：检测探测完成的策略并自动触发 LLM 审查。"""
    triggered = asyncio.run(_check_probing_strategies())
    if triggered:
        logger.info("Beat: triggered probe review for %d strategy(s)", triggered)
    return {"triggered": triggered}


@celery_app.task(name="strategies.auto_collection_check", bind=True, max_retries=0)
def auto_collection_check_task(self) -> dict:
    """Beat 触发：检测全量采集完成的策略并自动建切片。"""
    triggered = asyncio.run(_check_collecting_strategies())
    if triggered:
        logger.info("Beat: auto-created slices for %d strategy(s)", triggered)
    return {"triggered": triggered}
