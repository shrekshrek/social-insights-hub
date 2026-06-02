"""知识库 Celery 异步任务 + APScheduler 爬取任务"""

import asyncio
import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """在 gevent threadpool 的真实 OS 线程中运行协程。

    gevent monkey-patch 后 worker greenlet 无法直接使用 asyncio；
    通过 gevent threadpool 在真实 OS 线程中调用 asyncio.run()。

    **为什么 KB 用 async + local engine，而 news_media/social_media 改为同步 SyncSessionLocal？**

    共享全局 `async_engine` 在 Celery gevent worker 下存在并发 dispose 竞态风险
    （多 greenlet 同时 dispose 会让 asyncpg 连接池进入损坏状态，greenlet 永久卡住）。
    两种合法规避策略：

    1. **同步路径**（social_media / news_media celery 任务）: 用 `SyncSessionLocal`
       + psycopg driver，gevent monkey-patch 底层 socket 自动让出。零 event loop 切换。
    2. **隔离 async 路径**（KB）: 每个任务在 `process_document_task` 里创建独立的
       `create_async_engine(poolclass=NullPool)`，用完 dispose。不接触共享的全局
       `async_engine`，因此没有竞态。

    KB 走 2 是因为其依赖（EmbeddingService 的 httpx.AsyncClient）是 async，改同步
    牵连较大；且 KB 并发度低（单文档处理），每任务一次 engine 握手开销可接受。
    """
    from gevent import get_hub

    return get_hub().threadpool.apply(asyncio.run, (coro,))


@celery_app.task(name="knowledge_base.process_document")
def process_document_task(document_id: int) -> None:
    """处理知识库文档（同步 Celery 任务包装器）

    内部通过 gevent threadpool 在真实 OS 线程中运行 asyncio。
    使用 NullPool 避免跨事件循环复用 asyncpg 连接池导致的
    "Future attached to a different loop" 错误（每次任务创建独立连接，用完即关）。
    失败时记录日志但不抛出，不触发 Celery 重试（文档状态已在 service 层写为 failed）。
    """
    from sqlalchemy.pool import NullPool
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from src.config import settings
    from src.knowledge_base.service import process_document

    async def _run() -> None:
        from src.knowledge_base.embedding import EmbeddingService

        db_url = str(settings.DATABASE_URL).replace(
            "postgresql+psycopg://", "postgresql+asyncpg://"
        )
        engine = create_async_engine(db_url, poolclass=NullPool)
        svc = EmbeddingService()
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                await process_document(db, document_id, embedding_svc=svc)
        finally:
            await engine.dispose()
            await svc._client.close()

    try:
        _run_async(_run())
    except Exception as e:
        logger.error("知识库文档 %d 处理任务异常: %s", document_id, e, exc_info=True)


async def crawl_source(source_type: str) -> dict:
    """触发指定来源爬取（APScheduler / BackgroundTasks 调用）。

    在 FastAPI asyncio 事件循环中原生运行，无需 gevent 桥接。
    返回 {source_type, new_docs, error}。
    """
    from src.database import AsyncSessionLocal
    from src.knowledge_base.crawlers.registry import CRAWLER_REGISTRY

    crawler_cls = CRAWLER_REGISTRY.get(source_type)
    if crawler_cls is None:
        return {
            "source_type": source_type,
            "new_docs": 0,
            "error": f"未知来源: {source_type}",
        }

    try:
        async with AsyncSessionLocal() as db:
            new_docs = await crawler_cls().run(db)
        logger.info("[%s] 爬取任务完成，新入库 %d 篇", source_type, new_docs)
        return {"source_type": source_type, "new_docs": new_docs, "error": None}
    except Exception as e:
        logger.error("[%s] 爬取任务异常: %s", source_type, e, exc_info=True)
        return {"source_type": source_type, "new_docs": 0, "error": str(e)}
