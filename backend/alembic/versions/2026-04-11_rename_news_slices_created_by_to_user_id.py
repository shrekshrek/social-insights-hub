"""rename_news_slices_created_by_to_user_id

与社媒 AnalysisSlice.user_id 对齐命名。

Revision ID: b2c3d4e5f6a0
Revises: a1b2c3d4e5f9
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a0"
down_revision: Union[str, None] = "a1b2c3d4e5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("news_slices", "created_by", new_column_name="user_id")


def downgrade() -> None:
    op.alter_column("news_slices", "user_id", new_column_name="created_by")
