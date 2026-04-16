"""add_profile_name_to_research_tasks

Revision ID: add_profile_name_research_tasks
Revises: add_audit_logs_table
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_profile_name_research_tasks"
down_revision: Union[str, Sequence[str]] = "add_audit_logs_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 research_tasks 表添加 profile_name 字段（industry / creative）。"""
    op.add_column(
        "research_tasks",
        sa.Column(
            "profile_name",
            sa.String(length=32),
            nullable=False,
            server_default="industry",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_tasks", "profile_name")
