"""add_cii_to_post_analysis

为 post_analysis 表添加 cii（内容互动指数）字段，
用于存储每条帖子的 Content Interaction Index。

CII 公式：
RawScore = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Collected × 3)
CII = log10(RawScore + 1) × 10

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2025-11-28 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i4d5e6f7g8h9"
down_revision: Union[str, Sequence[str], None] = "h3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 cii 字段"""

    # 添加 cii 列到 post_analysis 表
    op.add_column(
        "post_analysis",
        sa.Column(
            "cii",
            sa.Float(),
            nullable=True,
            comment="内容互动指数 (Content Interaction Index)，基于互动数据计算",
        ),
    )


def downgrade() -> None:
    """移除 cii 字段"""

    op.drop_column("post_analysis", "cii")
