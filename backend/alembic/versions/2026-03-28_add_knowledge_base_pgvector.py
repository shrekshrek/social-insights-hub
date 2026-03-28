"""add knowledge base pgvector

Revision ID: 20260328_knowledge_base
Revises: 20260326_brief_subject
Create Date: 2026-03-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260328_knowledge_base"
down_revision: str | None = "20260326_brief_subject"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 启用 pgvector 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. 创建 knowledge_documents 表
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="upload"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column(
            "industry_tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "processing_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_documents_workspace_id",
        "knowledge_documents",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    op.create_index(
        "ix_knowledge_documents_source_type",
        "knowledge_documents",
        ["source_type"],
        unique=False,
    )

    # 3. 创建 knowledge_chunks 表（embedding 列用 raw SQL 添加，autogenerate 不支持 vector 类型）
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 手写 embedding 列（vector 类型，autogenerate 不支持）
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1024) NOT NULL DEFAULT array_fill(0, ARRAY[1024])::vector(1024)")
    # 移除临时默认值（不应持久存在）
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding DROP DEFAULT")

    op.create_index(
        "ix_knowledge_chunks_document_id",
        "knowledge_chunks",
        ["document_id"],
        unique=False,
    )

    # 4. 手写 IVFFlat 索引（autogenerate 不支持）
    op.execute(
        "CREATE INDEX ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    # Note: vector extension is not dropped as other components may depend on it
