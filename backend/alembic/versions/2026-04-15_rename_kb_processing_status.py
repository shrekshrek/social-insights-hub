"""rename knowledge_documents.processing_status to status

Revision ID: rename_kb_processing_status
Revises: align_jobs_news_tasks
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op

revision: str = "rename_kb_processing_status"
down_revision: Union[str, Sequence[str]] = "align_jobs_news_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "knowledge_documents",
        "processing_status",
        new_column_name="status",
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_documents",
        "status",
        new_column_name="processing_status",
    )
