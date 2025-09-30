from celery import Celery

from src.config import settings

celery_app = Celery(
    __name__,
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[],  # No task modules currently - add here when needed
)

celery_app.conf.update(
    task_track_started=True,
)

# A more robust way for task discovery might be needed for larger apps,
# but explicit inclusion is clear and effective for this structure.
