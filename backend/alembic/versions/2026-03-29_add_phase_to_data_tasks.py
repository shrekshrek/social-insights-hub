"""add phase column to social_data_tasks

Revision ID: 82000f2fde50
Revises: 9a32f9bb1db7
Create Date: 2026-03-29

探测任务（phase='probe'）和全量采集任务（phase='collect'）分离，
以 phase 字段标识，均归属同一 Monitor，可按 phase 筛选显示。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "82000f2fde50"
down_revision: Union[str, Sequence[str], None] = "9a32f9bb1db7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "social_data_tasks",
        sa.Column("phase", sa.String(20), nullable=True),
    )

    # 存量数据迁移：
    # - 有 probe_size 参数且处于探测相关状态 → probe
    # - 其余（已完成全量采集、普通任务等）→ collect
    op.execute(
        """
        UPDATE social_data_tasks
        SET phase = 'probe'
        WHERE (task_params->>'probe_size') IS NOT NULL
          AND status IN ('pending', 'accepted', 'running', 'probe_ready', 'failed')
        """
    )
    op.execute(
        """
        UPDATE social_data_tasks
        SET phase = 'collect'
        WHERE phase IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("social_data_tasks", "phase")
