"""add unique constraint on knowledge_documents(source_type, source_url)

Revision ID: 9a32f9bb1db7
Revises: 20260328_knowledge_base
Create Date: 2026-03-28

防止同一 URL 被重复爬取入库。NULL source_url（用户上传）不受约束（PostgreSQL NULL != NULL）。
"""

from typing import Sequence, Union

from alembic import op

revision: str = "9a32f9bb1db7"
down_revision: Union[str, Sequence[str], None] = "20260328_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_knowledge_documents_source_type_url",
        "knowledge_documents",
        ["source_type", "source_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_documents_source_type_url",
        "knowledge_documents",
    )
