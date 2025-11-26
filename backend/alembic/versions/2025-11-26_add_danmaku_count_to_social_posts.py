"""add_danmaku_count_to_social_posts

为 social_posts 表添加 danmaku_count（弹幕数）字段，
这是B站平台特有的互动数据。

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2025-11-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h3c4d5e6f7g8'
down_revision: Union[str, Sequence[str], None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 danmaku_count 字段"""

    # 添加 danmaku_count 列到 social_posts 表
    op.add_column(
        'social_posts',
        sa.Column(
            'danmaku_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='弹幕数(B站特有)'
        )
    )


def downgrade() -> None:
    """移除 danmaku_count 字段"""

    op.drop_column('social_posts', 'danmaku_count')
