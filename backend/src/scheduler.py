"""APScheduler: 轻量定时任务（替代 Celery Beat）

所有任务均在 FastAPI asyncio 事件循环中原生运行，无需 gevent 桥接。
Celery 保留 AI 分析流水线 + 文档处理（需要进程隔离的长时任务）。

⚠️ 必须单 worker 部署约束
AsyncIOScheduler 绑定单一 asyncio 事件循环，每个 uvicorn worker 进程都会
独立启动一份 scheduler 实例，多 worker 时会导致所有定时任务重复执行 N 次
（LLM 多倍调用、KB 爬虫多倍请求等）。`docker-compose.prod.yml` 和
`backend/Dockerfile` 都已显式 `--workers 1`，与本地 dev 环境对齐。
若将来确实需要横向扩容（用户量、CPU 占用持续打满）才考虑下列任一方案：
  - Redis SETNX leader election（只让 leader worker 启动 scheduler）
  - 改用 Celery Beat（独立进程跑定时任务）
  - APScheduler SQLAlchemyJobStore + 分布式锁
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
