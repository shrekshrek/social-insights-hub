"""APScheduler: 轻量定时任务（替代 Celery Beat）

所有任务均在 FastAPI asyncio 事件循环中原生运行，无需 gevent 桥接。
Celery 保留 AI 分析流水线 + 文档处理（需要进程隔离的长时任务）。

注意：AsyncIOScheduler 绑定单一 asyncio 事件循环，不支持多进程/多副本部署。
本项目 docker-compose 使用单 uvicorn worker，此约束不影响当前部署。
若将来需要横向扩容，可迁移至 APScheduler SQLAlchemyJobStore（带分布式锁）。
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    from src.strategies.tasks import (
        check_collecting_strategies,
        check_probing_strategies,
        reset_stuck_news_tasks,
    )

    scheduler.add_job(
        check_probing_strategies,
        "interval",
        minutes=2,
        id="strategy_probe",
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        check_collecting_strategies,
        "interval",
        minutes=2,
        id="strategy_collection",
        max_instances=1,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        reset_stuck_news_tasks,
        "interval",
        minutes=5,
        id="news_task_watchdog",
        max_instances=1,
        misfire_grace_time=60,
    )

    from src.agent.tasks import reset_timed_out_tasks

    scheduler.add_job(
        reset_timed_out_tasks,
        "interval",
        minutes=5,
        id="agent_timeout_reset",
        max_instances=1,
        misfire_grace_time=120,
    )

    from src.knowledge_base.tasks import crawl_source

    scheduler.add_job(
        crawl_source,
        "cron",
        args=["nbs"],
        day=1,
        hour=3,
        minute=0,
        id="crawl_nbs",
        max_instances=1,
        misfire_grace_time=3600,  # 月度任务：1 小时内补执行
    )
    scheduler.add_job(
        crawl_source,
        "cron",
        args=["cnnic"],
        day=15,
        hour=3,
        minute=0,
        id="crawl_cnnic",
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        crawl_source,
        "cron",
        args=["govsite"],
        day_of_week=0,
        hour=4,
        minute=0,
        id="crawl_govsite",
        max_instances=1,
        misfire_grace_time=3600,  # 周任务：1 小时内补执行
    )

    return scheduler
