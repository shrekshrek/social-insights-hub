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

celery_app.autodiscover_tasks(["src.tasks"], force=True)
