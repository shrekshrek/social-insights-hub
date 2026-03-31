"""知识库数据模型"""

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    pass


class KnowledgeDocument(Base):
    """知识库文档

    存储市场知识库中的文档元数据。支持平台公共文档（workspace_id IS NULL）
    和用户私有上传（workspace_id = user_id）。
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        Integer(), nullable=True, index=False, comment="NULL=平台公共；user_id=用户私有上传"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="文档标题")
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="upload",
        server_default="upload",
        comment="来源类型: upload / cnnic / nbs / govsite / cninfo",
    )
    source_url: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="公共数据来源链接"
    )
    source_meta: Mapped[dict | None] = mapped_column(
        JSONB(), nullable=True, comment="年份、报告类型等元信息"
    )
    file_name: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="原始文件名"
    )
    file_path: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="服务器本地文件路径，用于查看原文"
    )
    industry_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        default=list,
        server_default="{}",
        comment="行业标签，用于检索过滤",
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer(), nullable=False, default=0, server_default="0", comment="处理后分块数"
    )
    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending / processing / ready / failed",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text(), nullable=True, comment="处理失败时的错误信息"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 关系
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    """知识库分块

    存储文档的文本分块和向量嵌入，用于 RAG 检索。
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(BigInteger(), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属文档 ID",
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False, comment="原文分块内容")
    embedding: Mapped[list[float]] = mapped_column(
        Vector(1024), nullable=False, comment="BAAI/bge-large-zh 向量嵌入（1024 维）"
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer(), nullable=False, comment="块序号（从 0 开始）"
    )
    chunk_meta: Mapped[dict | None] = mapped_column(
        JSONB(), nullable=True, comment="页码、章节等元信息"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 关系
    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument", back_populates="chunks"
    )
