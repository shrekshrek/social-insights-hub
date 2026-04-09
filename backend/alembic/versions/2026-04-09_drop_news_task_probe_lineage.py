"""drop probe_round and parent_probe_id from news_tasks

独立 news monitor 不再支持 probe/refine 流程，lineage 字段作废。
strategy 研究场景的 probe 轮次由 strategies.probe_round 表达。

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_news_tasks_parent_probe_id", table_name="news_tasks")
    op.drop_constraint("fk_news_tasks_parent_probe_id", "news_tasks", type_="foreignkey")
    op.drop_column("news_tasks", "parent_probe_id")
    op.drop_column("news_tasks", "probe_round")


def downgrade() -> None:
    op.add_column(
        "news_tasks",
        sa.Column(
            "probe_round",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "news_tasks",
        sa.Column("parent_probe_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_news_tasks_parent_probe_id",
        "news_tasks",
        "news_tasks",
        ["parent_probe_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_news_tasks_parent_probe_id",
        "news_tasks",
        ["parent_probe_id"],
    )
