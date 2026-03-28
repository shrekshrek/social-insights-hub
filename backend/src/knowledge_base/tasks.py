"""知识库 Celery 异步任务"""

import asyncio
import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="knowledge_base.process_document")
def process_document_task(document_id: int) -> None:
    """处理知识库文档（同步 Celery 任务包装器）

    内部通过 asyncio.run 调用 service.process_document。
    失败时记录日志但不抛出，不触发 Celery 重试（文档状态已在 service 层写为 failed）。
    """
    from src.database import AsyncSessionLocal
    from src.knowledge_base.service import process_document

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await process_document(db, document_id)

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error("知识库文档 %d 处理任务异常: %s", document_id, e, exc_info=True)
