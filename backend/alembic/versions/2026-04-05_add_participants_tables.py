"""add participants tables: rename monitor_participants, add news_monitor_participants and strategy_participants

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a1
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 重命名 monitor_participants → social_monitor_participants
    op.rename_table("monitor_participants", "social_monitor_participants")

    # 2. 新增 news_monitor_participants
    op.create_table(
        "news_monitor_participants",
        sa.Column(
            "monitor_id",
            sa.Integer,
            sa.ForeignKey("news_monitors.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # 3. 新增 strategy_participants
    op.create_table(
        "strategy_participants",
        sa.Column(
            "strategy_id",
            sa.Integer,
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("strategy_participants")
    op.drop_table("news_monitor_participants")
    op.rename_table("social_monitor_participants", "monitor_participants")
