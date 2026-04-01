"""refactor strategy-task relation: add strategy_id FK, rename monitor_id, drop task_ids

Revision ID: c1a2b3d4e5f6
Revises: b30499e4bd19
Create Date: 2026-04-01

Phase 0: 消灭 strategy.task_ids JSON 数组，改用 DataTask.strategy_id FK 反查。
同时将 strategy.monitor_id 重命名为 social_monitor_id，为 news_media 预留命名空间。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b30499e4bd19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. social_data_tasks 加 strategy_id 可空 FK
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            nullable=True,
            comment="所属策略 ID（策略流程专用，普通任务为 NULL）",
        ),
    )
    op.create_index(
        "ix_social_data_tasks_strategy_id", "social_data_tasks", ["strategy_id"]
    )

    # 2. 回填：从 strategy.task_ids JSON 数组反写 strategy_id
    op.execute(
        """
        UPDATE social_data_tasks dt
        SET strategy_id = s.id
        FROM strategies s
        WHERE dt.id = ANY(
            SELECT (elem)::integer
            FROM strategies s2,
                 jsonb_array_elements_text(s2.task_ids::jsonb) AS elem
            WHERE s2.id = s.id
        )
        """
    )

    # 3. strategies 重命名 monitor_id → social_monitor_id
    op.alter_column("strategies", "monitor_id", new_column_name="social_monitor_id")

    # 4. 删除 strategies.task_ids 列
    op.drop_column("strategies", "task_ids")


def downgrade() -> None:
    # 恢复 task_ids 列（空数组，回填数据需手工处理）
    op.add_column(
        "strategies",
        sa.Column(
            "task_ids",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="策略创建的所有 DataTask ID",
        ),
    )

    # 从 FK 反写 task_ids（按 probe 阶段任务回填，仅近似还原）
    op.execute(
        """
        UPDATE strategies s
        SET task_ids = COALESCE(
            (
                SELECT jsonb_agg(dt.id)
                FROM social_data_tasks dt
                WHERE dt.strategy_id = s.id
                  AND dt.is_deleted = FALSE
            ),
            '[]'::jsonb
        )
        """
    )

    # 还原 social_monitor_id → monitor_id
    op.alter_column("strategies", "social_monitor_id", new_column_name="monitor_id")

    # 删除 social_data_tasks.strategy_id
    op.drop_index("ix_social_data_tasks_strategy_id", table_name="social_data_tasks")
    op.drop_column("social_data_tasks", "strategy_id")
