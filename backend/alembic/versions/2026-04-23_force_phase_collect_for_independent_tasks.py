"""force phase=collect for independent tasks

Revision ID: force_phase_collect
Revises: drop_strategy_slices
Create Date: 2026-04-23 00:00:00.000000

将 social_tasks / news_tasks 的 phase 字段从 nullable 提升为 NOT NULL DEFAULT 'collect'。

背景：phase 字段原本只在策略流程使用（probe/collect 两段式），独立 monitor 任务历史
上 phase=NULL（社媒）或 phase 由用户表单选择（新闻，默认 probe，与后端 execute 端点
拒绝独立 probe 的设计相悖）。统一收口：独立任务一律 collect，probe 仅策略流程使用。

迁移步骤（顺序敏感）：
  1. 把"独立 monitor + 异常 phase"的存量数据 backfill 成 collect：
     - phase IS NULL 的全部记录 → collect
     - phase='probe' 且 strategy_id IS NULL 的记录 → collect（用户表单误选）
  2. 给两张表的 phase 列增加 server_default='collect'
  3. 把 phase 列设为 NOT NULL（执行前所有 NULL 已被步骤 1 清理）

策略流程任务（strategy_id IS NOT NULL）的 phase=probe 不动，保留策略两段式语义。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'force_phase_collect'
down_revision: Union[str, Sequence[str], None] = 'drop_strategy_slices'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ===== social_tasks =====
    bind.execute(sa.text(
        """
        UPDATE social_tasks
        SET phase = 'collect'
        WHERE phase IS NULL
           OR (phase = 'probe' AND strategy_id IS NULL)
        """
    ))
    op.alter_column(
        "social_tasks",
        "phase",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="collect",
    )

    # ===== news_tasks =====
    bind.execute(sa.text(
        """
        UPDATE news_tasks
        SET phase = 'collect'
        WHERE phase IS NULL
           OR (phase = 'probe' AND strategy_id IS NULL)
        """
    ))
    op.alter_column(
        "news_tasks",
        "phase",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="collect",
    )


def downgrade() -> None:
    op.alter_column(
        "news_tasks",
        "phase",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "social_tasks",
        "phase",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    # 注意：downgrade 不还原 backfill 的数据，存量 phase 维持 'collect'。
    # 若需还原历史 NULL/probe，应通过备份恢复。
