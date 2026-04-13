"""add_title_to_research_tasks

Revision ID: 376d3d880214
Revises: a0b1c2d3e4f5
Create Date: 2026-04-13 06:13:45.166121

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '376d3d880214'
down_revision: Union[str, None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'research_tasks',
        sa.Column('title', sa.String(200), nullable=True, comment='研究标题（可选，planner 自动生成）'),
    )


def downgrade() -> None:
    op.drop_column('research_tasks', 'title')
