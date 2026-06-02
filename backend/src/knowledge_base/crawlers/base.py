"""公开数据爬取基类

定义 BaseCrawler 抽象接口和通用的文档 upsert 逻辑。
子类只需实现 discover() 返回待入库内容列表。
"""

import base64
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import NamedTuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.knowledge_base.models import KnowledgeDocument
from src.knowledge_base.tasks import process_document_task

logger = logging.getLogger(__name__)


class CrawlSource(NamedTuple):
    """单条待入库内容"""

    url: str  # 原始 URL（用于去重）
    title: str
    file_bytes: bytes  # PDF 字节 或 Markdown → UTF-8 编码字节
    filename: str  # "report.pdf" 或 "content.md"
    source_meta: dict  # 年份、期次等元信息


class BaseCrawler(ABC):
    """公开数据爬取基类

    子类需定义 source_type 类属性，并实现 discover()。
    通用的去重、入库、任务派发逻辑在 run() / _upsert() 中实现。
    """

    source_type: str  # 子类定义，如 "cnnic" / "nbs" / "govsite"

    @abstractmethod
    async def discover(self) -> list[CrawlSource]:
        """发现待入库内容列表。子类实现具体爬取逻辑。"""

    async def run(self, db: AsyncSession) -> int:
        """执行爬取，返回新入库文档数"""
        logger.info("[%s] 开始爬取", self.source_type)
        try:
            sources = await self.discover()
        except Exception as e:
            logger.error("[%s] discover() 失败: %s", self.source_type, e, exc_info=True)
            return 0

        count = 0
        for src in sources:
            try:
                skipped = await self._upsert(db, src)
                if not skipped:
                    count += 1
            except Exception as e:
                logger.warning(
                    "[%s] upsert 失败 url=%s: %s", self.source_type, src.url, e
                )

        logger.info("[%s] 爬取完成，新入库 %d 篇", self.source_type, count)
        return count

    async def _upsert(self, db: AsyncSession, src: CrawlSource) -> bool:
        """插入或重试文档，派发处理任务。

        Returns:
            True  — 已存在且状态正常，跳过
            False — 新建或重试，已派发处理任务
        """
        result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source_type == self.source_type,
                KnowledgeDocument.source_url == src.url,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.status in ("ready", "processing", "pending"):
                return True  # 跳过

            # status = failed → 重置重试
            existing.status = "pending"
            existing.error_message = None
            existing.source_meta = {
                **dict(src.source_meta),
                "_file_bytes_b64": base64.b64encode(src.file_bytes).decode(),
            }
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            process_document_task.delay(existing.id)
            return False

        doc = KnowledgeDocument(
            workspace_id=None,  # 平台公共文档
            title=src.title,
            source_type=self.source_type,
            source_url=src.url,
            file_name=src.filename,
            status="pending",
            source_meta={
                **dict(src.source_meta),
                "_file_bytes_b64": base64.b64encode(src.file_bytes).decode(),
            },
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        process_document_task.delay(doc.id)
        return False

    async def _crawl_url(self, url: str, query: str = "") -> str:
        """调用 Crawl4AI REST API，返回 fit_markdown 正文。

        query 非空时启用 BM25 过滤，只保留相关段落。
        """
        payload: dict = {
            "urls": [url],
            "crawler_config": {
                "cache_mode": "bypass",
                "scan_full_page": True,
                "page_timeout": 30000,
            },
        }
        if query:
            payload["markdown_generator"] = {
                "content_filter": {
                    "type": "bm25",
                    "query": query,
                    "threshold": 1.0,
                }
            }

        headers = {}
        if settings.CRAWL4AI_TOKEN:
            headers["Authorization"] = f"Bearer {settings.CRAWL4AI_TOKEN}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.CRAWL4AI_BASE_URL}/crawl",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        if not results:
            raise ValueError(f"Crawl4AI 返回空结果: {url}")

        markdown = results[0].get("markdown", {})
        # 优先 fit_markdown（BM25 过滤后），无则 raw_markdown
        content = markdown.get("fit_markdown") or markdown.get("raw_markdown", "")
        if not content.strip():
            raise ValueError(f"Crawl4AI 返回空内容: {url}")

        return content
