"""知识库业务逻辑

包含文档解析、分块、向量化、RAG 检索和 CRUD 操作。
"""

import io
import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils import run_cpu_bound_task
from .embedding import EmbeddingService, get_embedding_service
from .models import KnowledgeChunk, KnowledgeDocument

logger = logging.getLogger(__name__)

# 文档大小上限（50MB）
_MAX_FILE_SIZE = 50 * 1024 * 1024

# 分块参数（BAAI/bge-m3 支持 8192 tokens，为检索召回粒度取 400 字符，可按需放大）
_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 50

# RAG 相似度阈值：低于此分数的 chunk 视为不相关，不注入 prompt
# 依据：当前 KB 以宏观统计/政策为主，品牌/品类 query 极易召回弱相关结果，
# 无阈值过滤会让 LLM 把噪声当背景引用
_RAG_MIN_SCORE = 0.5


def parse_text(file_bytes: bytes, filename: str) -> str:
    """从文件字节提取纯文本

    支持：PDF（pdfplumber + DeepSeek-OCR fallback）/ DOCX（python-docx）/ TXT / MD。
    文件大小上限由 router 层校验（50MB）。

    PDF：pdfplumber 直出文本流；字符稀疏页（图片化表格、infographic 等）
    fallback 到 DeepSeek-OCR via SiliconFlow（OpenAI-compatible），输出 Markdown。
    OCR 调用失败优雅降级到 pdfplumber 原始文本，不阻塞主流程。详见 .ocr 模块。
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        from .ocr import extract_pdf_with_ocr_fallback

        return extract_pdf_with_ocr_fallback(file_bytes)

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


async def process_document(db: AsyncSession, doc_id: int, embedding_svc: EmbeddingService | None = None) -> None:
    """解析 → 分块 → 向量化 → 批量写入 knowledge_chunks → 更新 status=ready

    异常时 status=failed + error_message，不抛出（Celery 任务不重试）。
    """
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None:
        logger.error("process_document: 文档 %d 不存在", doc_id)
        return

    try:
        doc.status = "processing"
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()

        # 读取原始文件字节（存储在 source_meta 中）
        file_bytes_b64 = (doc.source_meta or {}).get("_file_bytes_b64")
        filename = doc.file_name or "document.txt"

        if file_bytes_b64 is None:
            raise ValueError("文档缺少原始文件字节，无法解析")

        import base64

        file_bytes = base64.b64decode(file_bytes_b64)

        # 保存原始文件到磁盘（供查看原文使用）
        from pathlib import Path
        storage_dir = Path("/app/storage/knowledge_base") / (doc.source_type or "upload")
        storage_dir.mkdir(parents=True, exist_ok=True)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        saved_path = storage_dir / f"{doc_id}.{ext}"
        saved_path.write_bytes(file_bytes)
        doc.file_path = str(saved_path)

        # 解析文本（CPU 密集型）
        raw_text = await run_cpu_bound_task(parse_text, file_bytes, filename)
        if not raw_text.strip():
            raise ValueError("文档内容为空，无法处理")

        # 分块（CPU 密集型）
        chunks = await run_cpu_bound_task(chunk_text, raw_text)
        if not chunks:
            raise ValueError("文档分块结果为空")

        # 向量化（CPU 密集型，批量处理）
        svc = embedding_svc or get_embedding_service()
        embeddings = await svc.embed(chunks)

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
        doc.status = "ready"
        doc.error_message = None
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("文档 %d 处理完成，共 %d 个分块", doc_id, len(chunks))

    except Exception as e:
        logger.error("文档 %d 处理失败: %s", doc_id, e, exc_info=True)
        try:
            doc = await db.get(KnowledgeDocument, doc_id)
            if doc:
                doc.status = "failed"
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
            .where(KnowledgeDocument.status == "ready")
            .where(filter_cond)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )

        result = await db.execute(stmt)
        rows = result.all()

        filtered = [r for r in rows if (r.score or 0) >= _RAG_MIN_SCORE]
        if not filtered:
            if rows:
                top_score = max((r.score or 0) for r in rows)
                logger.info(
                    "retrieve_market_context: top_score=%.3f 未达阈值 %.2f，降级为空",
                    top_score, _RAG_MIN_SCORE,
                )
            return ""

        parts = ["## 市场背景参考资料\n"]
        for row in filtered:
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
        query = query.where(KnowledgeDocument.status == status)

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
    """删除文档及所有分块（CASCADE），同时清理磁盘文件"""
    import os
    file_path = doc.file_path
    await db.delete(doc)
    await db.commit()
    if file_path:
        try:
            os.remove(file_path)
        except OSError:
            logger.warning("删除文件失败（已忽略）: %s", file_path)
