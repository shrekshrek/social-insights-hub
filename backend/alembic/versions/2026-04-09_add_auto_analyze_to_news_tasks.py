"""add auto_analyze column to news_tasks

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_tasks",
        sa.Column(
            "auto_analyze",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="采集完成后是否自动触发分析链（对标 SocialTask.auto_analyze）",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_tasks", "auto_analyze")
