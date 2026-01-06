"""add auto_analyze to data_tasks

Revision ID: add_auto_analyze
Revises: 2025-12-29_add_agent_task_fields
Create Date: 2026-01-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "n4d5e6f7g8h9"
down_revision: Union[str, None] = "m3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "auto_analyze",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="数据上传完成后自动执行全流程分析",
        ),
    )


def downgrade() -> None:
    op.drop_column("social_data_tasks", "auto_analyze")
