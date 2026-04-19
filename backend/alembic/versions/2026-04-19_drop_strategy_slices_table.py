"""drop_strategy_slices_table

Revision ID: drop_strategy_slices
Revises: ad108e1b5e36
Create Date: 2026-04-19 00:00:00.000000

移除 strategy_slices 关联表：社媒切片改为通过 social_monitor_id 隐式关联，
与新闻切片（NewsSlice.monitor_id）语义对称。

Pre-check 保险：迁移前校验不存在跨 monitor 的历史遗留引用。
因为策略研究是自动化闭环（Monitor 由策略 confirm_research 时专属创建），
此校验应始终返回 0 行；若非 0 说明存在需人工清理的数据，中止迁移。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'drop_strategy_slices'
down_revision: Union[str, Sequence[str], None] = 'ad108e1b5e36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 保险校验：不应存在跨 monitor 引用
    mismatch_count = bind.execute(sa.text(
        """
        SELECT count(*) FROM strategy_slices ss
        JOIN social_slices s ON ss.slice_id = s.id
        JOIN strategies st ON ss.strategy_id = st.id
        WHERE st.social_monitor_id IS NULL
           OR s.monitor_id != st.social_monitor_id
        """
    )).scalar() or 0
    if mismatch_count > 0:
        raise RuntimeError(
            f"strategy_slices 存在 {mismatch_count} 条跨 monitor 引用，"
            "不符合『每个策略独占一个 monitor』的设计假设。"
            "迁移中止，请人工核查 strategy_slices 数据。"
        )

    op.drop_index("idx_strategy_slices_slice_id", table_name="strategy_slices")
    op.drop_table("strategy_slices")


def downgrade() -> None:
    op.create_table(
        "strategy_slices",
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("slice_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["slice_id"],
            ["social_slices.id"],
            name=op.f("fk_strategy_slices_slice_id_social_slices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_strategy_slices_strategy_id_strategies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "strategy_id", "slice_id", name=op.f("pk_strategy_slices")
        ),
    )
    op.create_index(
        "idx_strategy_slices_slice_id",
        "strategy_slices",
        ["slice_id"],
        unique=False,
    )
