"""add_snapshot_name_column

为 project_analysis_snapshots 表添加 name 字段（可选）。

Revision ID: l2b3c4d5e6f7
Revises: k1a2b3c4d5e6
Create Date: 2025-12-17 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "l2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "k1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_analysis_snapshots",
        sa.Column("name", sa.String(255), nullable=True, comment="快照名称（可选）"),
    )


def downgrade() -> None:
    op.drop_column("project_analysis_snapshots", "name")
