"""unify user fk + social slice fields + pg naming cleanup

统一字段命名与清理历史遗留：

1. P1a  social_tasks.creator_id -> user_id
2. P1b  strategies.created_by   -> user_id
3. P2   social_slices 补齐 status / stats / error_message 字段，
        result_data 改为 nullable
4. P3   清理 social_tasks / strategies / social_slices 表的 PG 内部命名残留
        （主键、序列、索引、FK 约束名）

Revision ID: d4e5f6a0b1c2
Revises: c3d4e5f6a0b1
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a0b1c2"
down_revision: Union[str, None] = "c3d4e5f6a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _safe(stmt: str) -> None:
    """执行可能因对象不存在而失败的 DDL，失败时静默跳过。

    PG 的 IF EXISTS 对 ALTER ... RENAME CONSTRAINT 不支持，必须 try/except。
    """
    try:
        op.execute(stmt)
    except Exception:
        pass


def upgrade() -> None:
    # ==========================================================
    # P1a: social_tasks.creator_id -> user_id
    # ==========================================================
    op.alter_column("social_tasks", "creator_id", new_column_name="user_id")

    # 自动索引 + FK 约束命名跟上
    _safe(
        'ALTER INDEX IF EXISTS "ix_social_data_tasks_creator_id" '
        'RENAME TO "ix_social_tasks_user_id"'
    )
    _safe(
        'ALTER TABLE social_tasks '
        'RENAME CONSTRAINT "fk_social_data_tasks_creator_id_users" '
        'TO "fk_social_tasks_user_id_users"'
    )

    # 顺带清理 social_tasks 表的其他历史 social_data_tasks 命名残留
    for old, new in [
        ("pk_social_data_tasks", "pk_social_tasks"),
    ]:
        _safe(f'ALTER TABLE social_tasks RENAME CONSTRAINT "{old}" TO "{new}"')
    for old, new in [
        ("ix_social_data_tasks_data_source", "ix_social_tasks_data_source"),
        ("ix_social_data_tasks_is_deleted", "ix_social_tasks_is_deleted"),
        ("ix_social_data_tasks_monitor_id", "ix_social_tasks_monitor_id"),
        ("ix_social_data_tasks_name", "ix_social_tasks_name"),
        ("ix_social_data_tasks_platform_id", "ix_social_tasks_platform_id"),
        ("ix_social_data_tasks_status", "ix_social_tasks_status"),
        ("ix_social_data_tasks_strategy_id", "ix_social_tasks_strategy_id"),
        ("ix_social_data_tasks_task_type", "ix_social_tasks_task_type"),
    ]:
        _safe(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')
    for old, new in [
        (
            "fk_social_data_tasks_monitor_id_social_monitors",
            "fk_social_tasks_monitor_id_social_monitors",
        ),
        (
            "fk_social_data_tasks_platform_id_platforms",
            "fk_social_tasks_platform_id_platforms",
        ),
        (
            "fk_social_data_tasks_strategy_id_strategies",
            "fk_social_tasks_strategy_id_strategies",
        ),
    ]:
        _safe(f'ALTER TABLE social_tasks RENAME CONSTRAINT "{old}" TO "{new}"')

    # ==========================================================
    # P1b: strategies.created_by -> user_id
    # ==========================================================
    op.alter_column("strategies", "created_by", new_column_name="user_id")

    _safe(
        'ALTER INDEX IF EXISTS "ix_strategies_created_by" '
        'RENAME TO "ix_strategies_user_id"'
    )
    _safe(
        'ALTER TABLE strategies '
        'RENAME CONSTRAINT "fk_strategies_created_by_users" '
        'TO "fk_strategies_user_id_users"'
    )

    # ==========================================================
    # P2: social_slices 补齐字段
    # ==========================================================
    op.add_column(
        "social_slices",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending | analyzing | completed | failed",
        ),
    )
    op.add_column(
        "social_slices",
        sa.Column(
            "stats",
            sa.JSON(),
            nullable=True,
            comment="统计摘要（任务数/原文数/评论数/情感分布等）",
        ),
    )
    op.add_column(
        "social_slices",
        sa.Column(
            "error_message",
            sa.String(length=1000),
            nullable=True,
            comment="失败原因",
        ),
    )

    # 历史数据 result_data 非空，放宽为 nullable
    op.alter_column("social_slices", "result_data", nullable=True)

    # ==========================================================
    # P3: social_slices 表的 PG 内部命名残留
    # ==========================================================
    # 主键 / 序列
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "pk_project_analysis_snapshots" '
        'TO "pk_social_slices"'
    )
    _safe(
        'ALTER SEQUENCE IF EXISTS project_analysis_snapshots_id_seq '
        'RENAME TO social_slices_id_seq'
    )

    # 丢弃冗余的 idx_social_slices_monitor（与 ix_social_slices_monitor_id 重复）
    _safe('DROP INDEX IF EXISTS "idx_social_slices_monitor"')

    # 重命名自动索引
    _safe(
        'ALTER INDEX IF EXISTS "ix_analysis_slices_monitor_id" '
        'RENAME TO "ix_social_slices_monitor_id"'
    )
    _safe(
        'ALTER INDEX IF EXISTS "ix_analysis_slices_user_id" '
        'RENAME TO "ix_social_slices_user_id"'
    )

    # 重命名 FK 约束
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "fk_analysis_slices_monitor_id_social_monitors" '
        'TO "fk_social_slices_monitor_id_social_monitors"'
    )
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "fk_project_analysis_snapshots_user_id_users" '
        'TO "fk_social_slices_user_id_users"'
    )


def downgrade() -> None:
    # P3 回滚（尽力）
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "fk_social_slices_user_id_users" '
        'TO "fk_project_analysis_snapshots_user_id_users"'
    )
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "fk_social_slices_monitor_id_social_monitors" '
        'TO "fk_analysis_slices_monitor_id_social_monitors"'
    )
    _safe(
        'ALTER INDEX IF EXISTS "ix_social_slices_user_id" '
        'RENAME TO "ix_analysis_slices_user_id"'
    )
    _safe(
        'ALTER INDEX IF EXISTS "ix_social_slices_monitor_id" '
        'RENAME TO "ix_analysis_slices_monitor_id"'
    )
    # 重建 idx_social_slices_monitor（原 migration 创建的）
    _safe(
        'CREATE INDEX IF NOT EXISTS "idx_social_slices_monitor" '
        'ON social_slices(monitor_id)'
    )
    _safe(
        'ALTER SEQUENCE IF EXISTS social_slices_id_seq '
        'RENAME TO project_analysis_snapshots_id_seq'
    )
    _safe(
        'ALTER TABLE social_slices '
        'RENAME CONSTRAINT "pk_social_slices" '
        'TO "pk_project_analysis_snapshots"'
    )

    # P2 回滚
    op.alter_column("social_slices", "result_data", nullable=False)
    op.drop_column("social_slices", "error_message")
    op.drop_column("social_slices", "stats")
    op.drop_column("social_slices", "status")

    # P1b 回滚
    _safe(
        'ALTER TABLE strategies '
        'RENAME CONSTRAINT "fk_strategies_user_id_users" '
        'TO "fk_strategies_created_by_users"'
    )
    _safe(
        'ALTER INDEX IF EXISTS "ix_strategies_user_id" '
        'RENAME TO "ix_strategies_created_by"'
    )
    op.alter_column("strategies", "user_id", new_column_name="created_by")

    # P1a 回滚
    for old, new in [
        (
            "fk_social_tasks_strategy_id_strategies",
            "fk_social_data_tasks_strategy_id_strategies",
        ),
        (
            "fk_social_tasks_platform_id_platforms",
            "fk_social_data_tasks_platform_id_platforms",
        ),
        (
            "fk_social_tasks_monitor_id_social_monitors",
            "fk_social_data_tasks_monitor_id_social_monitors",
        ),
    ]:
        _safe(f'ALTER TABLE social_tasks RENAME CONSTRAINT "{old}" TO "{new}"')
    for old, new in [
        ("ix_social_tasks_task_type", "ix_social_data_tasks_task_type"),
        ("ix_social_tasks_strategy_id", "ix_social_data_tasks_strategy_id"),
        ("ix_social_tasks_status", "ix_social_data_tasks_status"),
        ("ix_social_tasks_platform_id", "ix_social_data_tasks_platform_id"),
        ("ix_social_tasks_name", "ix_social_data_tasks_name"),
        ("ix_social_tasks_monitor_id", "ix_social_data_tasks_monitor_id"),
        ("ix_social_tasks_is_deleted", "ix_social_data_tasks_is_deleted"),
        ("ix_social_tasks_data_source", "ix_social_data_tasks_data_source"),
    ]:
        _safe(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')
    _safe(
        'ALTER TABLE social_tasks '
        'RENAME CONSTRAINT "pk_social_tasks" TO "pk_social_data_tasks"'
    )
    _safe(
        'ALTER TABLE social_tasks '
        'RENAME CONSTRAINT "fk_social_tasks_user_id_users" '
        'TO "fk_social_data_tasks_creator_id_users"'
    )
    _safe(
        'ALTER INDEX IF EXISTS "ix_social_tasks_user_id" '
        'RENAME TO "ix_social_data_tasks_creator_id"'
    )
    op.alter_column("social_tasks", "user_id", new_column_name="creator_id")
