"""知识库 API 端点"""

import base64
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.database import get_async_db
from src.pagination import PaginationParams, get_pagination_params
from src.schemas import MessageResponse, PaginatedResponse

from . import service
from .models import KnowledgeDocument
from .schemas import (
    DocumentRead,
    DocumentUploadResponse,
    SearchRequest,
    SearchResponse,
    ChunkResult,
)
from .tasks import process_document_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["Knowledge Base"])

# 文件大小上限：50MB
_MAX_FILE_SIZE = 50 * 1024 * 1024

# 支持的文件类型
_SUPPORTED_EXTENSIONS = {"pdf", "docx", "txt", "md"}


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传知识库文档",
)
async def upload_document(
    file: UploadFile,
    title: str | None = Form(None, description="文档标题（留空则使用文件名）"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """上传文档到知识库，触发后台 Celery 处理（解析→分块→向量化）

    支持格式：PDF / DOCX / TXT / MD，大小上限 50MB。
    """
    # 校验文件类型
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的文件类型 .{ext}，支持：{', '.join(_SUPPORTED_EXTENSIONS)}",
        )

    # 读取文件内容
    file_bytes = await file.read()

    # 校验文件大小
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件大小超过上限（50MB），当前 {len(file_bytes) // 1024 // 1024}MB",
        )

    doc_title = title or filename

    # 创建文档记录，将文件字节暂存在 source_meta 中供 Celery worker 使用
    doc = KnowledgeDocument(
        workspace_id=current_user.id,
        title=doc_title,
        source_type="upload",
        file_name=filename,
        processing_status="pending",
        source_meta={"_file_bytes_b64": base64.b64encode(file_bytes).decode()},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # 派发 Celery 处理任务
    process_document_task.delay(doc.id)
    logger.info("文档 %d 上传完成，已派发处理任务", doc.id)

    return DocumentUploadResponse(id=doc.id, title=doc.title, processing_status=doc.processing_status)


@router.get(
    "/documents",
    response_model=PaginatedResponse[DocumentRead],
    status_code=status.HTTP_200_OK,
    summary="知识库文档列表",
)
async def list_documents(
    source_type: str | None = Query(None, description="来源类型过滤"),
    processing_status: str | None = Query(None, description="处理状态过滤"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    pagination: PaginationParams = Depends(get_pagination_params),
):
    """获取知识库文档列表（平台公共 + 当前用户私有）"""
    items, total = await service.list_documents(
        db,
        workspace_id=current_user.id,
        source_type=source_type,
        status=processing_status,
        skip=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse[DocumentRead].create(
        items=[DocumentRead.model_validate(item) for item in items],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentRead,
    status_code=status.HTTP_200_OK,
    summary="知识库文档详情",
)
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定文档详情（含处理状态）"""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {doc_id} 不存在",
        )
    # 权限校验：平台公共（workspace_id IS NULL）或当前用户私有
    if doc.workspace_id is not None and doc.workspace_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该文档",
        )
    return DocumentRead.model_validate(doc)


@router.delete(
    "/documents/{doc_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="删除知识库文档",
)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """删除文档及所有向量分块"""
    doc = await service.get_document(db, doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {doc_id} 不存在",
        )
    # 只有文档所有者可以删除（平台公共文档需 admin 权限，暂不实现）
    if doc.workspace_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有文档上传者可以删除该文档",
        )
    await service.delete_document(db, doc)
    return MessageResponse(message=f"文档 {doc_id} 已删除")


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="RAG 检索测试",
)
async def search_documents(
    request: SearchRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    """测试 RAG 检索，返回与查询最相关的分块"""
    from .embedding import get_embedding_service
    from .models import KnowledgeChunk
    from sqlalchemy import or_, select

    embedding_svc = get_embedding_service()
    query_vec = (await embedding_svc.embed([request.query]))[0]

    from .models import KnowledgeDocument

    stmt = (
        select(
            KnowledgeChunk.content,
            KnowledgeChunk.chunk_index,
            KnowledgeChunk.document_id,
            KnowledgeDocument.title,
            (1 - KnowledgeChunk.embedding.cosine_distance(query_vec)).label("score"),
        )
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(KnowledgeDocument.processing_status == "ready")
        .where(
            or_(
                KnowledgeDocument.workspace_id.is_(None),
                KnowledgeDocument.workspace_id == current_user.id,
            )
        )
        .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
        .limit(request.top_k)
    )

    result = await db.execute(stmt)
    rows = result.all()

    chunk_results = [
        ChunkResult(
            document_id=row.document_id,
            document_title=row.title,
            content=row.content,
            score=float(row.score),
            chunk_index=row.chunk_index,
        )
        for row in rows
    ]

    return SearchResponse(
        query=request.query,
        results=chunk_results,
        total=len(chunk_results),
    )
