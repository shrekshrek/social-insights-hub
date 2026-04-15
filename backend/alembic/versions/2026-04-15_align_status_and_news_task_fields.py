"""align analysis_jobs status and add news_task timing fields

- analysis_jobs: rename status value 'processing' -> 'running' (data migration)
- news_tasks: add started_at and completed_at columns

Revision ID: align_jobs_news_tasks
Revises: rename_owner_id_monitors
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "align_jobs_news_tasks"
down_revision: Union[str, Sequence[str]] = "rename_owner_id_monitors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate analysis_jobs status: 'processing' -> 'running'
    op.execute(
        "UPDATE analysis_jobs SET status = 'running' WHERE status = 'processing'"
    )

    # 2. Add started_at and completed_at to news_tasks
    op.add_column(
        "news_tasks",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="任务开始时间",
        ),
    )
    op.add_column(
        "news_tasks",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="任务完成时间",
        ),
    )


def downgrade() -> None:
    # Revert news_tasks columns
    op.drop_column("news_tasks", "completed_at")
    op.drop_column("news_tasks", "started_at")

    # Revert analysis_jobs status: 'running' -> 'processing'
    op.execute(
        "UPDATE analysis_jobs SET status = 'processing' WHERE status = 'running'"
    )
