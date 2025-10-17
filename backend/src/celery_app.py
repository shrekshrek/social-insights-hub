from celery import Celery

from src.config import settings

celery_app = Celery(
    __name__,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_track_started=True,
)

# Celery worker 启动时会自动 import 这个模块的任务
# 通过 include 配置让 Celery 知道从哪里加载任务
celery_app.conf.update(
    include=["src.tasks.worker"]
)
