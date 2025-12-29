"""add_collected_count_to_social_posts

为 social_posts 表添加 collected_count（收藏数）字段，
并为现有的互动数据字段添加注释。

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2025-11-26 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 collected_count 字段"""

    # 添加 collected_count 列到 social_posts 表
    op.add_column(
        "social_posts",
        sa.Column(
            "collected_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="收藏数",
        ),
    )


def downgrade() -> None:
    """移除 collected_count 字段"""

    op.drop_column("social_posts", "collected_count")
