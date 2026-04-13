"""add progress to research_tasks

Revision ID: add_progress_research_tasks
Revises: add_title_to_research_tasks
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa

revision = "add_progress_research_tasks"
down_revision = "376d3d880214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_tasks",
        sa.Column(
            "progress",
            sa.JSON(),
            nullable=True,
            comment="研究执行进度日志，每个节点完成后追加一条",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "progress")
