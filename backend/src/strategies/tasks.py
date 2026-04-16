"""策略定时任务（由 APScheduler 在 FastAPI asyncio 事件循环中调度）

主动检测策略状态，替代原有「前端轮询才能触发」的设计缺陷：
- check_probing_strategies:       探测任务全部分析完成 → 自动触发 LLM 审查
- check_collecting_strategies:    全量采集全部完成   → 自动触发建切片 + 覆盖度验证
- reset_stuck_news_probe_tasks:   超时的 running 新闻探测任务 → 自动标记为 failed
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update

from src.database import AsyncSessionLocal

# 新闻探测任务终态：completed（采集成功）或 failed（失败/超时）
_NEWS_PROBE_TERMINAL = {"completed", "failed"}

# 新闻探测任务超时阈值（分钟）：超过此时长仍为 running 视为卡死
_NEWS_PROBE_TIMEOUT_MINUTES = 20

logger = logging.getLogger(__name__)


async def check_probing_strategies() -> int:
    """找出所有探测完成但尚未触发审查的策略，触发 LLM 审查。

    1. 查询 status=probing 且 probe_review_result=None 的策略
    2. 确认所有 probe 任务（社媒 + 新闻）均已完成分析
    3. 调用 _run_probe_review_bg_task（内部自开 session，与本函数 session 无冲突）
    """
    from src.strategies.models import Strategy
    from src.strategies.service import (
        _build_probe_task_summaries,
        _probe_review_in_progress,
        _run_probe_review_bg_task,
    )
    from src.social_media.tasks.models import SocialTask
    from src.news_media.tasks.service import get_news_tasks_by_strategy

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

            # 查询该策略的所有社媒 probe 任务
            tasks_result = await db.execute(
                select(SocialTask).where(
                    and_(
                        SocialTask.strategy_id == strategy.id,
                        SocialTask.phase == "probe",
                        SocialTask.is_deleted.is_(False),
                    )
                )
            )
            probe_tasks = list(tasks_result.scalars().all())

            # 查询该策略的所有新闻 probe 任务
            news_probe_tasks = await get_news_tasks_by_strategy(db, strategy.id, phase="probe")

            if not probe_tasks and not news_probe_tasks:
                continue

            task_ids = [t.id for t in probe_tasks]
            task_statuses, analyzed_summaries = await _build_probe_task_summaries(
                db, task_ids
            )

            # 社媒任务全部已分析
            social_all_analyzed = bool(task_statuses) and all(
                t.has_analysis for t in task_statuses
            )
            # 新闻任务全部已终态（completed 或 failed 均视为完成，不再阻塞）
            news_all_analyzed = (
                all(t.status in _NEWS_PROBE_TERMINAL for t in news_probe_tasks)
                if news_probe_tasks
                else True
            )

            if social_all_analyzed and news_all_analyzed:
                to_review.append((strategy.id, analyzed_summaries))

    # 在 session 关闭后调用，_run_probe_review_bg_task 内部自开 session
    for strategy_id, analyzed_summaries in to_review:
        if strategy_id not in _probe_review_in_progress:
            _probe_review_in_progress.add(strategy_id)
            await _run_probe_review_bg_task(strategy_id, analyzed_summaries)
            logger.info("Strategy %d: probe review triggered by scheduler", strategy_id)

    return len(to_review)


async def check_collecting_strategies() -> int:
    """找出全量采集完成但尚未建切片的策略，触发自动建切片 + 覆盖度验证。

    1. 查询 status=collecting 且无 StrategySlice 的策略
    2. 确认所有 collect 任务（社媒 + 新闻）均 completed 且已有分析结果
    3. 调用 _create_auto_slices（内部 commit，不需要外层提交）
    """
    from src.social_media.tasks.models import SocialTask
    from src.strategies.models import Strategy, StrategySlice
    from src.strategies.service import _create_auto_slices, get_strategy_by_id
    from src.news_media.tasks.service import get_news_tasks_by_strategy

    triggered = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.status == "collecting")
        )
        strategies = result.scalars().all()

        for strategy in strategies:
            # 查询该策略的所有社媒 collect 任务
            tasks_result = await db.execute(
                select(SocialTask).where(
                    and_(
                        SocialTask.strategy_id == strategy.id,
                        SocialTask.phase == "collect",
                        SocialTask.is_deleted.is_(False),
                    )
                )
            )
            tasks = list(tasks_result.scalars().all())

            # 查询该策略的所有新闻 collect 任务
            news_tasks = await get_news_tasks_by_strategy(db, strategy.id, phase="collect")

            if not tasks and not news_tasks:
                continue

            # 社媒任务全部完成且有分析
            if not all(t.status == "completed" for t in tasks):
                continue
            if not all(t.analysis_result is not None for t in tasks):
                continue

            # 新闻任务全部完成且有分析
            if not all(t.status == "completed" for t in news_tasks):
                continue
            if not all(t.analysis_result is not None for t in news_tasks):
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
                    db, full_strategy, tasks, current_user_id=strategy.user_id,
                    news_tasks=news_tasks,
                )
                triggered += 1
                logger.info(
                    "Strategy %d: slices auto-created by scheduler", strategy.id
                )
            except Exception as e:
                logger.error(
                    "Strategy %d: auto-slice creation failed: %s",
                    strategy.id,
                    e,
                    exc_info=True,
                )

    return triggered


async def reset_stuck_news_probe_tasks() -> int:
    """将超时的新闻探测任务（running 超过阈值时间）标记为 failed。

    Celery Worker 崩溃时任务状态可能永远停留在 running，此 watchdog 负责回收，
    使 check_probing_strategies 能正常检测到"全部终态"并触发 LLM 审查。
    """
    from src.news_media.tasks.models import NewsTask

    timeout_before = datetime.now(tz=timezone.utc) - timedelta(minutes=_NEWS_PROBE_TIMEOUT_MINUTES)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(NewsTask)
            .where(
                and_(
                    NewsTask.status == "running",
                    NewsTask.phase == "probe",
                    NewsTask.strategy_id.is_not(None),
                    NewsTask.started_at < timeout_before,
                )
            )
            .values(
                status="failed",
                error_message=f"任务超时（>{_NEWS_PROBE_TIMEOUT_MINUTES} 分钟仍未完成，watchdog 自动标记）",
            )
            .returning(NewsTask.id)
        )
        stuck_ids = list(result.scalars().all())
        if stuck_ids:
            await db.commit()
            logger.warning(
                "Watchdog: reset %d stuck news probe tasks → failed: %s",
                len(stuck_ids),
                stuck_ids,
            )

    return len(stuck_ids)
