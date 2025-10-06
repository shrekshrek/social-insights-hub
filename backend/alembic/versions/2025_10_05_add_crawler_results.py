"""add crawler note results table

Revision ID: 2025_10_05_002
Revises: 2025_10_05_001
Create Date: 2025-10-05 09:30:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2025_10_05_002"
down_revision: Union[str, None] = "2025_10_05_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawler_note_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("note_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column("raw_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["task_id"], ["crawler_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crawler_note_results_task_id"),
        "crawler_note_results",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_note_results_note_id"),
        "crawler_note_results",
        ["note_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_crawler_note_results_note_id"), table_name="crawler_note_results"
    )
    op.drop_index(
        op.f("ix_crawler_note_results_task_id"), table_name="crawler_note_results"
    )
    op.drop_table("crawler_note_results")
