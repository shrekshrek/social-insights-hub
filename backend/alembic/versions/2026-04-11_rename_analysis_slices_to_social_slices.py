"""rename_analysis_slices_to_social_slices

重命名 analysis_slices 表为 social_slices，与 NewsSlice（news_slices）对称。
同时更新索引名和外键约束名。

Revision ID: c3d4e5f6a0b1
Revises: b2c3d4e5f6a8
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a0b1"
down_revision: Union[str, None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 重命名主表
    op.rename_table("analysis_slices", "social_slices")

    # 2. 重命名索引（适配新表名）
    #    旧名来自历史迁移，可能是 idx_monitor_slices_* 或 idx_analysis_slices_*
    for old_name, new_name in [
        ("idx_monitor_slices_project", "idx_social_slices_monitor"),
        ("idx_analysis_slices_monitor", "idx_social_slices_monitor"),
        ("idx_monitor_slices_created_at", "idx_social_slices_created_at"),
        ("idx_analysis_slices_created_at", "idx_social_slices_created_at"),
    ]:
        try:
            op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')
        except Exception:
            pass  # index may not exist under this name

    # 3. 重命名 strategy_slices 外键约束（引用新表名）
    try:
        op.execute(
            'ALTER TABLE strategy_slices '
            'RENAME CONSTRAINT "fk_strategy_slices_slice_id_analysis_slices" '
            'TO "fk_strategy_slices_slice_id_social_slices"'
        )
    except Exception:
        pass  # constraint may have a different auto-generated name


def downgrade() -> None:
    op.rename_table("social_slices", "analysis_slices")

    for old_name, new_name in [
        ("idx_social_slices_monitor", "idx_monitor_slices_project"),
        ("idx_social_slices_created_at", "idx_monitor_slices_created_at"),
    ]:
        try:
            op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')
        except Exception:
            pass

    try:
        op.execute(
            'ALTER TABLE strategy_slices '
            'RENAME CONSTRAINT "fk_strategy_slices_slice_id_social_slices" '
            'TO "fk_strategy_slices_slice_id_analysis_slices"'
        )
    except Exception:
        pass
