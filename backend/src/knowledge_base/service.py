"""知识库业务逻辑

包含文档解析、分块、向量化、RAG 检索和 CRUD 操作。
"""

import io
import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils import run_cpu_bound_task
from .embedding import get_embedding_service
from .models import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger(__name__)

# 文档大小上限（50MB）
_MAX_FILE_SIZE = 50 * 1024 * 1024

# 分块参数（SiliconFlow BAAI/bge-large-zh 上限 512 tokens，中文约 1字/token，留余量取 400）
_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 50


def parse_text(file_bytes: bytes, filename: str) -> str:
    """从文件字节提取纯文本

    支持：PDF（pdfplumber）/ DOCX（python-docx）/ TXT / MD。
    文件大小上限由 router 层校验（50MB）。
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)

    if ext == "docx":
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    # TXT / MD — UTF-8 with fallback to GBK
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("gbk", errors="replace")


def chunk_text(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """按字符分块，中文友好（不在单词中间截断）

    使用滑动窗口分块，连续空白合并为单个换行，避免中文断词。
    空文本返回空列表。
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # 如果不是最后一块，尝试在换行处截断，避免语义割裂
        if end < text_len:
            # 向前找最近的换行符（最多回退 50 个字符）
            newline_pos = text.rfind("\n", start, end)
            if newline_pos > start + chunk_size // 2:
                end = newline_pos + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < text_len else text_len

    return chunks


async def process_document(db: AsyncSession, doc_id: int) -> None:
    """解析 → 分块 → 向量化 → 批量写入 knowledge_chunks → 更新 status=ready

    异常时 status=failed + error_message，不抛出（Celery 任务不重试）。
    """
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None:
        logger.error("process_document: 文档 %d 不存在", doc_id)
        return

    try:
        doc.processing_status = "processing"
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()

        # 读取原始文件字节（存储在 source_meta 中）
        file_bytes_b64 = (doc.source_meta or {}).get("_file_bytes_b64")
        filename = doc.file_name or "document.txt"

        if file_bytes_b64 is None:
            raise ValueError("文档缺少原始文件字节，无法解析")

        import base64

        file_bytes = base64.b64decode(file_bytes_b64)

        # 解析文本（CPU 密集型）
        raw_text = await run_cpu_bound_task(parse_text, file_bytes, filename)
        if not raw_text.strip():
            raise ValueError("文档内容为空，无法处理")

        # 分块（CPU 密集型）
        chunks = await run_cpu_bound_task(chunk_text, raw_text)
        if not chunks:
            raise ValueError("文档分块结果为空")

        # 向量化（CPU 密集型，批量处理）
        embedding_svc = get_embedding_service()
        embeddings = await embedding_svc.embed(chunks)

        # 删除旧分块（重新处理时）
        old_chunks = await db.execute(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
        )
        for old_chunk in old_chunks.scalars().all():
            await db.delete(old_chunk)

        # 批量写入新分块
        for idx, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            db.add(
                KnowledgeChunk(
                    document_id=doc_id,
                    content=content,
                    embedding=embedding,
                    chunk_index=idx,
                )
            )

        # 清除存储的文件字节（节省空间）
        source_meta = dict(doc.source_meta or {})
        source_meta.pop("_file_bytes_b64", None)
        doc.source_meta = source_meta if source_meta else None

        doc.chunk_count = len(chunks)
        doc.processing_status = "ready"
        doc.error_message = None
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("文档 %d 处理完成，共 %d 个分块", doc_id, len(chunks))

    except Exception as e:
        logger.error("文档 %d 处理失败: %s", doc_id, e, exc_info=True)
        try:
            doc = await db.get(KnowledgeDocument, doc_id)
            if doc:
                doc.processing_status = "failed"
                doc.error_message = str(e)[:500]
                doc.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as db_err:
            logger.error("更新文档 %d 失败状态时出错: %s", doc_id, db_err)


async def retrieve_market_context(
    db: AsyncSession,
    query: str,
    user_id: int | None = None,
    top_k: int = 6,
) -> str:
    """pgvector 余弦相似度检索，返回格式化的市场背景段落

    检索范围：
    - workspace_id IS NULL（平台公共）
    - OR workspace_id = user_id（用户私有）

    无匹配结果时返回 ""，不阻塞策略生成主流程。
    """
    if not query.strip():
        return ""

    try:
        embedding_svc = get_embedding_service()
        query_vec = (await embedding_svc.embed([query]))[0]

        # pgvector 余弦相似度（<=> 操作符）
        # 过滤条件：平台公共 OR 用户私有
        filter_cond = or_(
            KnowledgeDocument.workspace_id.is_(None),
            KnowledgeDocument.workspace_id == user_id,
        ) if user_id is not None else KnowledgeDocument.workspace_id.is_(None)

        stmt = (
            select(
                KnowledgeChunk.content,
                KnowledgeChunk.chunk_index,
                KnowledgeDocument.title,
                (1 - KnowledgeChunk.embedding.cosine_distance(query_vec)).label("score"),
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.processing_status == "ready")
            .where(filter_cond)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return ""

        parts = ["## 市场背景参考资料\n"]
        for row in rows:
            parts.append(f"**来源：{row.title}**\n{row.content}\n")

        return "\n".join(parts)

    except Exception as e:
        logger.warning("retrieve_market_context 检索失败（降级为空）: %s", e)
        return ""


async def list_documents(
    db: AsyncSession,
    workspace_id: int | None,
    source_type: str | None,
    status: str | None,
    skip: int,
    limit: int,
) -> tuple[list[KnowledgeDocument], int]:
    """文档列表（分页 + source_type/status 过滤）"""
    query = select(KnowledgeDocument)

    if workspace_id is not None:
        query = query.where(
            or_(
                KnowledgeDocument.workspace_id.is_(None),
                KnowledgeDocument.workspace_id == workspace_id,
            )
        )

    if source_type:
        query = query.where(KnowledgeDocument.source_type == source_type)

    if status:
        query = query.where(KnowledgeDocument.processing_status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(KnowledgeDocument.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_document(db: AsyncSession, doc_id: int) -> KnowledgeDocument | None:
    """按 ID 获取文档"""
    return await db.get(KnowledgeDocument, doc_id)


async def delete_document(db: AsyncSession, doc: KnowledgeDocument) -> None:
    """删除文档及所有分块（CASCADE）"""
    await db.delete(doc)
    await db.commit()
