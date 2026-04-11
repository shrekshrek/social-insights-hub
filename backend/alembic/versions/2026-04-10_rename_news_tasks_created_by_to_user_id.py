"""rename news_tasks created_by to user_id

Revision ID: 230d35bb79d5
Revises: b2c3d4e5f6a0
Create Date: 2026-04-10 19:21:31.891722

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '230d35bb79d5'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("news_tasks", "created_by", new_column_name="user_id")


def downgrade() -> None:
    op.alter_column("news_tasks", "user_id", new_column_name="created_by")
