"""add probe_round and parent_probe_id to news_tasks

Phase A of news_media probe/collect 分家:
- probe_round: int default 1 — refine 时 +1
- parent_probe_id: FK → news_tasks.id, SET NULL — collect 指向 approve 它的 probe;
  refine 产生的 probe 指向上一轮 probe

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_tasks",
        sa.Column(
            "probe_round",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="探测轮次（refine 一次 +1，仅 probe 任务有意义）",
        ),
    )
    op.add_column(
        "news_tasks",
        sa.Column(
            "parent_probe_id",
            sa.Integer(),
            nullable=True,
            comment="父级 probe 任务 ID",
        ),
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


def downgrade() -> None:
    op.drop_index("ix_news_tasks_parent_probe_id", table_name="news_tasks")
    op.drop_constraint("fk_news_tasks_parent_probe_id", "news_tasks", type_="foreignkey")
    op.drop_column("news_tasks", "parent_probe_id")
    op.drop_column("news_tasks", "probe_round")
