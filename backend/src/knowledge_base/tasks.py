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


def _run_crawler(source_type: str) -> dict:
    """公共爬取执行逻辑，返回 {source_type, new_docs, error}"""
    from src.database import AsyncSessionLocal
    from src.knowledge_base.crawlers.registry import CRAWLER_REGISTRY

    crawler_cls = CRAWLER_REGISTRY.get(source_type)
    if crawler_cls is None:
        return {"source_type": source_type, "new_docs": 0, "error": f"未知来源: {source_type}"}

    async def _run() -> int:
        async with AsyncSessionLocal() as db:
            return await crawler_cls().run(db)

    try:
        new_docs = asyncio.run(_run())
        logger.info("[%s] 爬取任务完成，新入库 %d 篇", source_type, new_docs)
        return {"source_type": source_type, "new_docs": new_docs, "error": None}
    except Exception as e:
        logger.error("[%s] 爬取任务异常: %s", source_type, e, exc_info=True)
        return {"source_type": source_type, "new_docs": 0, "error": str(e)}


@celery_app.task(name="knowledge_base.crawl_source")
def crawl_source_task(source_type: str) -> dict:
    """触发指定来源爬取，返回 {source_type, new_docs, error}"""
    return _run_crawler(source_type)


@celery_app.task(name="knowledge_base.crawl_cnnic")
def crawl_cnnic_task() -> None:
    _run_crawler("cnnic")


@celery_app.task(name="knowledge_base.crawl_nbs")
def crawl_nbs_task() -> None:
    _run_crawler("nbs")


@celery_app.task(name="knowledge_base.crawl_govsite")
def crawl_govsite_task() -> None:
    _run_crawler("govsite")
