"""策略定时任务（由 APScheduler 在 FastAPI asyncio 事件循环中调度）

主动检测策略状态，替代原有「前端轮询才能触发」的设计缺陷：
- check_probing_strategies:       探测任务全部分析完成 → 自动触发 LLM 审查
- check_collecting_strategies:    全量采集全部完成   → 自动触发建切片 + 覆盖度验证
- reset_stuck_news_tasks:         超时的 running/pending 新闻任务（probe + collect）→ 自动标记为 failed
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
    """找出处于 collecting 态的策略，驱动两阶段推进：

    阶段 A：全量采集任务完成 + 已分析 → 自动建切片（仍在 collecting）
    阶段 B：切片已建 + 所有切片 Stage2 完成 + coverage 尚未跑 →
             跑 coverage_check，通过则推进到 ready

    两阶段幂等、彼此独立。用户端前端轮询 get_collection_status 会更快触发
    阶段 B，此处仅作 2min 兜底（防前端停止轮询后永久卡住）。
    """
    from src.social_media.tasks.models import SocialTask
    from src.social_media.analysis.models import SocialSlice
    from src.strategies.models import Strategy
    from src.strategies.service import (
        _create_auto_slices,
        _slice_creation_in_progress,
        _try_advance_to_ready,
        get_strategy_by_id,
    )
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

            # 社媒任务全部到达终态（completed / failed）
            social_terminal = {"completed", "failed"}
            if not all(t.status in social_terminal for t in tasks):
                continue
            # 至少有一个 completed 且有分析结果的社媒任务
            completed_social = [t for t in tasks if t.status == "completed" and t.analysis_result is not None]
            if not completed_social:
                continue

            # 新闻任务全部到达终态
            news_terminal = {"completed", "failed"}
            if not all(t.status in news_terminal for t in news_tasks):
                continue
            # 新闻允许全部 failed（新闻是补充数据源，不阻塞）
            completed_news = [t for t in news_tasks if t.status == "completed" and t.analysis_result is not None]

            # 幂等保护：社媒切片 + 新闻切片是否已建（按 monitor_id 判定）
            has_social = False
            if strategy.social_monitor_id:
                existing_social = await db.execute(
                    select(SocialSlice.id)
                    .where(SocialSlice.monitor_id == strategy.social_monitor_id)
                    .limit(1)
                )
                has_social = existing_social.scalar_one_or_none() is not None
            else:
                has_social = not completed_social  # 无社媒 monitor 视为已"完成"

            has_news = False
            if strategy.news_monitor_id:
                from src.news_media.analysis.models import NewsSlice as _NS
                existing_news = await db.execute(
                    select(_NS.id).where(_NS.monitor_id == strategy.news_monitor_id).limit(1)
                )
                has_news = existing_news.scalar_one_or_none() is not None
            else:
                has_news = not completed_news  # 无新闻 monitor 视为已"完成"

            # 阶段 A：切片尚未建 → 建切片（保持 collecting，由后续轮次或 get_collection_status 推进 ready）
            # 幂等保护：跳过 polling 正在创建中的策略，避免与 get_collection_status 重入
            # （_create_auto_slices 内部按 monitor_id+name 跳过已存在切片，本检查为额外防御）
            if not (has_social and has_news) and strategy.id not in _slice_creation_in_progress:
                _slice_creation_in_progress.add(strategy.id)
                try:
                    full_strategy = await get_strategy_by_id(db, strategy.id)
                    await _create_auto_slices(
                        db, full_strategy, completed_social, current_user_id=strategy.user_id,
                        news_tasks=completed_news,
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
                finally:
                    _slice_creation_in_progress.discard(strategy.id)
                continue

            # 阶段 B：切片已建 + coverage 未跑 → 尝试推进到 ready
            if strategy.coverage_check_result is None:
                try:
                    full_strategy = await get_strategy_by_id(db, strategy.id)
                    advanced = await _try_advance_to_ready(db, full_strategy)
                    if advanced:
                        triggered += 1
                        logger.info(
                            "Strategy %d: advanced to ready by scheduler", strategy.id
                        )
                except Exception as e:
                    logger.error(
                        "Strategy %d: _try_advance_to_ready failed: %s",
                        strategy.id,
                        e,
                        exc_info=True,
                    )

    return triggered


async def reset_stuck_news_tasks() -> int:
    """将超时的策略新闻任务（probe + collect）标记为 failed。

    覆盖场景：
    - probe running/pending 超时：Celery Worker 崩溃或宕机
    - collect running/pending 超时：同上（gevent + asyncio.run 兼容问题等）

    以 created_at 超过阈值为判断依据（started_at 可能为 NULL）。
    """
    from src.news_media.tasks.models import NewsTask
    from sqlalchemy import or_

    timeout_before = datetime.now(tz=timezone.utc) - timedelta(minutes=_NEWS_PROBE_TIMEOUT_MINUTES)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(NewsTask)
            .where(
                and_(
                    NewsTask.strategy_id.is_not(None),
                    or_(
                        and_(NewsTask.status == "running", NewsTask.created_at < timeout_before),
                        and_(NewsTask.status == "pending", NewsTask.created_at < timeout_before),
                    ),
                )
            )
            .values(
                status="failed",
                error_message=f"任务超时（>{_NEWS_PROBE_TIMEOUT_MINUTES} 分钟仍未完成，watchdog 自动标记）",
            )
            .returning(NewsTask.id, NewsTask.phase)
        )
        stuck_rows = result.all()
        if stuck_rows:
            await db.commit()
            stuck_ids = [r[0] for r in stuck_rows]
            logger.warning(
                "Watchdog: reset %d stuck news tasks → failed: %s",
                len(stuck_ids),
                [(r[0], r[1]) for r in stuck_rows],
            )
            return len(stuck_ids)

    return 0
