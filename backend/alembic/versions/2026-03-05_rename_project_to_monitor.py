"""rename project to monitor

Revision ID: 20260305_proj_to_mon
Revises: e395faad75d4
Create Date: 2026-03-05

Rename tables:
  - social_projects -> monitors
  - social_project_participants -> monitor_participants
  - project_analysis_slices -> analysis_slices

Rename columns:
  - social_data_tasks.project_id -> monitor_id
  - analysis_jobs.project_id -> monitor_id
  - analysis_slices.project_id -> monitor_id
  - monitor_participants.project_id -> monitor_id
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260305_proj_to_mon"
down_revision: Union[str, Sequence[str], None] = "e395faad75d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ── 1. Rename tables ──────────────────────────────────────────
    op.rename_table("social_projects", "monitors")
    op.rename_table("social_project_participants", "monitor_participants")
    op.rename_table("project_analysis_slices", "analysis_slices")

    # ── 1b. Rename date columns on monitors ─────────────────────
    op.alter_column("monitors", "project_start_date", new_column_name="start_date")
    op.alter_column("monitors", "project_end_date", new_column_name="end_date")

    # ── 2. Rename FK columns: project_id -> monitor_id ────────────

    # 2a. monitor_participants (composite PK)
    # Drop old FK first, rename column, recreate FK
    op.drop_constraint(
        "fk_social_project_participants_project_id_social_projects",
        "monitor_participants",
        type_="foreignkey",
    )
    op.alter_column(
        "monitor_participants", "project_id", new_column_name="monitor_id"
    )
    op.create_foreign_key(
        "fk_monitor_participants_monitor_id_monitors",
        "monitor_participants",
        "monitors",
        ["monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 2b. social_data_tasks.project_id -> monitor_id
    op.drop_constraint(
        "fk_social_data_tasks_project_id_social_projects",
        "social_data_tasks",
        type_="foreignkey",
    )
    op.drop_index("ix_social_data_tasks_project_id", table_name="social_data_tasks")
    op.alter_column(
        "social_data_tasks", "project_id", new_column_name="monitor_id"
    )
    op.create_foreign_key(
        "fk_social_data_tasks_monitor_id_monitors",
        "social_data_tasks",
        "monitors",
        ["monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_social_data_tasks_monitor_id",
        "social_data_tasks",
        ["monitor_id"],
        unique=False,
    )

    # 2c. analysis_jobs.project_id -> monitor_id
    op.drop_constraint(
        "fk_analysis_jobs_project_id_social_projects",
        "analysis_jobs",
        type_="foreignkey",
    )
    op.drop_index("idx_analysis_job_project", table_name="analysis_jobs")
    op.alter_column(
        "analysis_jobs", "project_id", new_column_name="monitor_id"
    )
    op.create_foreign_key(
        "fk_analysis_jobs_monitor_id_monitors",
        "analysis_jobs",
        "monitors",
        ["monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_analysis_job_monitor",
        "analysis_jobs",
        ["monitor_id"],
        unique=False,
    )

    # 2d. analysis_slices.project_id -> monitor_id
    op.drop_constraint(
        "fk_project_analysis_snapshots_project_id_social_projects",
        "analysis_slices",
        type_="foreignkey",
    )
    op.drop_index("idx_project_slices_project", table_name="analysis_slices")
    op.alter_column(
        "analysis_slices", "project_id", new_column_name="monitor_id"
    )
    op.create_foreign_key(
        "fk_analysis_slices_monitor_id_monitors",
        "analysis_slices",
        "monitors",
        ["monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_analysis_slices_monitor",
        "analysis_slices",
        ["monitor_id"],
        unique=False,
    )

    # ── 3. Update strategy_slices FK to point to new table name ───
    op.drop_constraint(
        "fk_strategy_slices_slice_id_project_analysis_slices",
        "strategy_slices",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_strategy_slices_slice_id_analysis_slices",
        "strategy_slices",
        "analysis_slices",
        ["slice_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── 4. Rename indexes on analysis_slices ──────────────────────
    op.drop_index("idx_project_slices_created_at", table_name="analysis_slices")
    op.create_index(
        "idx_analysis_slices_created_at",
        "analysis_slices",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse index rename
    op.drop_index("idx_analysis_slices_created_at", table_name="analysis_slices")
    op.create_index(
        "idx_project_slices_created_at", "analysis_slices", ["created_at"], unique=False
    )

    # Reverse strategy_slices FK
    op.drop_constraint(
        "fk_strategy_slices_slice_id_analysis_slices",
        "strategy_slices",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_strategy_slices_slice_id_project_analysis_slices",
        "strategy_slices",
        "analysis_slices",
        ["slice_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Reverse analysis_slices.monitor_id -> project_id
    op.drop_constraint(
        "fk_analysis_slices_monitor_id_monitors",
        "analysis_slices",
        type_="foreignkey",
    )
    op.drop_index("idx_analysis_slices_monitor", table_name="analysis_slices")
    op.alter_column("analysis_slices", "monitor_id", new_column_name="project_id")
    op.create_foreign_key(
        "fk_project_analysis_snapshots_project_id_social_projects",
        "analysis_slices",
        "monitors",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_project_slices_project", "analysis_slices", ["project_id"], unique=False)

    # Reverse analysis_jobs.monitor_id -> project_id
    op.drop_constraint(
        "fk_analysis_jobs_monitor_id_monitors",
        "analysis_jobs",
        type_="foreignkey",
    )
    op.drop_index("idx_analysis_job_monitor", table_name="analysis_jobs")
    op.alter_column("analysis_jobs", "monitor_id", new_column_name="project_id")
    op.create_foreign_key(
        "fk_analysis_jobs_project_id_social_projects",
        "analysis_jobs",
        "monitors",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_analysis_job_project", "analysis_jobs", ["project_id"], unique=False)

    # Reverse social_data_tasks.monitor_id -> project_id
    op.drop_constraint(
        "fk_social_data_tasks_monitor_id_monitors",
        "social_data_tasks",
        type_="foreignkey",
    )
    op.drop_index("ix_social_data_tasks_monitor_id", table_name="social_data_tasks")
    op.alter_column("social_data_tasks", "monitor_id", new_column_name="project_id")
    op.create_foreign_key(
        "fk_social_data_tasks_project_id_social_projects",
        "social_data_tasks",
        "monitors",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_social_data_tasks_project_id", "social_data_tasks", ["project_id"], unique=False)

    # Reverse monitor_participants.monitor_id -> project_id
    op.drop_constraint(
        "fk_monitor_participants_monitor_id_monitors",
        "monitor_participants",
        type_="foreignkey",
    )
    op.alter_column("monitor_participants", "monitor_id", new_column_name="project_id")
    op.create_foreign_key(
        "fk_social_project_participants_project_id_social_projects",
        "monitor_participants",
        "monitors",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Reverse date column renames
    op.alter_column("monitors", "start_date", new_column_name="project_start_date")
    op.alter_column("monitors", "end_date", new_column_name="project_end_date")

    # Reverse table renames
    op.rename_table("analysis_slices", "project_analysis_slices")
    op.rename_table("monitor_participants", "social_project_participants")
    op.rename_table("monitors", "social_projects")
