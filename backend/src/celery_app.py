"""Celery异步任务配置

配置Celery应用用于处理异步任务，特别是AI分析任务。
使用Redis作为消息代理和结果后端。

优化配置用于：
- AI数据筛选任务
- AI深度分析任务
- 主题聚类任务
- 竞品分析任务

技术说明：
- 使用 gevent pool 实现高并发（100协程）
- Celery 自动处理 gevent monkey patching（无需手动patch）
- Psycopg3 原生支持 gevent，无需额外补丁库
- 参考：https://docs.celeryq.dev/en/stable/userguide/concurrency/gevent.html
"""

import logging
from celery import Celery
from src.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "social_insights_hub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.social_media.analysis.celery_tasks.screening_tasks",
        "src.social_media.analysis.celery_tasks.deep_analysis_tasks",
        "src.social_media.analysis.celery_tasks.aggregation_tasks",
        "src.social_media.analysis.celery_tasks.monitor_slice_tasks",
        "src.social_media.analysis.celery_tasks.auto_analysis_tasks",
        "src.knowledge_base.tasks",
        # Future task modules:
        # "src.social_media.analysis.celery_tasks.clustering_tasks",
        # "src.social_media.analysis.celery_tasks.competitive_tasks",
    ],
)

# 详细的Celery配置
celery_app.conf.update(
    # ========== 任务序列化 ==========
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # ========== 时区和编码 ==========
    timezone="Asia/Shanghai",  # 使用中国时区
    enable_utc=True,
    # ========== 任务跟踪 ==========
    task_track_started=True,  # 跟踪任务启动状态
    task_send_sent_event=True,  # 发送任务发送事件
    # ========== 任务超时配置 ==========
    task_time_limit=7200,  # 硬超时：2小时（用于长时间AI任务）
    task_soft_time_limit=6600,  # 软超时：1小时50分钟
    # ========== Worker配置 ==========
    worker_prefetch_multiplier=1,  # 每次只预取1个任务，避免内存堆积
    worker_max_tasks_per_child=100,  # 每个worker进程最多执行100个任务后重启
    worker_disable_rate_limits=False,  # 启用速率限制
    # ========== 结果配置 ==========
    result_extended=True,  # 启用扩展任务结果属性
    result_expires=86400,  # 结果过期时间：24小时
    result_backend_transport_options={
        "master_name": "mymaster",
    },
    # ========== 连接配置 ==========
    broker_connection_retry_on_startup=True,  # 启动时自动重试连接
    broker_connection_retry=True,  # 连接断开后自动重试
    broker_connection_max_retries=10,  # 最多重试10次
    # ========== 任务路由配置（预留，后续模块使用） ==========
    # task_routes={
    #     "ai.screening.*": {"queue": "screening"},
    #     "ai.analysis.*": {"queue": "analysis"},
    #     "ai.clustering.*": {"queue": "clustering"},
    # },
    # ========== 任务优先级配置（预留） ==========
    # task_default_priority=5,
    # task_inherit_parent_priority=True,
    # ========== 错误处理 ==========
    task_acks_late=True,  # 任务执行完成后才确认（防止任务丢失）
    task_reject_on_worker_lost=True,  # Worker丢失时拒绝任务
    # ========== 性能优化 ==========
    # worker_pool 通过命令行参数指定
    # worker_concurrency 通过命令行参数指定
)

logger.info("Celery app configured (task_time_limit=7200s)")
