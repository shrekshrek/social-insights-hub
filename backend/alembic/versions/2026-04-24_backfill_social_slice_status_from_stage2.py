"""backfill SocialSlice.status from pipeline.stage2.status

Revision ID: backfill_slice_status_stage2
Revises: force_phase_collect
Create Date: 2026-04-24 00:00:00.000000

语义切换：SocialSlice.status 从"Stage3 完成"改为"Stage2 完成即 completed"，
与 NewsSlice.status 对齐；Stage3 的 3 报告失败不再回退 status。

迁移步骤：
  1. Stage2 = completed 或 skipped 的老切片 → status=completed（之前可能是 pending/failed）
  2. Stage2 = failed 的老切片 → status=failed（若之前是 pending 则显式标失败）

背景：新代码 `load_strategy_inputs` 按 status=completed 过滤。老库里存在
"Stage2/3 已完成但 status=pending" 的遗留记录（orchestrator 早期版本路径未
覆盖或 commit 丢失），若不 backfill，这些切片将被新的 gate 过滤掉导致下游
生成无数据。Stage3 失败但 Stage2 成功的切片（如果有）也应视为可用。

对 Stage2 仍 pending/processing 的切片不动（celery 进行中或崩溃，语义保持）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'backfill_slice_status_stage2'
down_revision: Union[str, Sequence[str], None] = 'force_phase_collect'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Stage2 终态 completed/skipped → 切片对下游可用 → status=completed
    bind.execute(sa.text(
        """
        UPDATE social_slices
        SET status = 'completed'
        WHERE status != 'completed'
          AND result_data->'pipeline'->'stage2'->>'status' IN ('completed', 'skipped')
        """
    ))

    # Stage2 终态 failed → 切片聚合失败 → status=failed（原来 status=pending 的显式标明）
    bind.execute(sa.text(
        """
        UPDATE social_slices
        SET status = 'failed'
        WHERE status = 'pending'
          AND result_data->'pipeline'->'stage2'->>'status' = 'failed'
        """
    ))


def downgrade() -> None:
    # 语义不可逆还原（老的 status 语义是"Stage3 完成"，无法从 pipeline 推断 Stage3 旧状态）。
    # 若需回滚，通过备份恢复 social_slices.status 列。
    pass
