"""rename snapshots to slices

Revision ID: 20260220_rename_snapshots_to_slices
Revises: n4d5e6f7g8h9
Create Date: 2026-02-20

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260220_snap_to_slice"
down_revision = "n4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename table
    op.rename_table("project_analysis_snapshots", "project_analysis_slices")

    # Rename indexes (PostgreSQL syntax)
    op.execute(
        "ALTER INDEX IF EXISTS idx_project_snapshots_project "
        "RENAME TO idx_project_slices_project"
    )
    op.execute(
        "ALTER INDEX IF EXISTS idx_project_snapshots_created_at "
        "RENAME TO idx_project_slices_created_at"
    )

    # Update analysis_type values in analysis_jobs
    op.execute(
        "UPDATE analysis_jobs "
        "SET analysis_type = 'project_slice_summary' "
        "WHERE analysis_type = 'project_snapshot_summary'"
    )

    # Update slice_id references in analysis_config JSON (for jobs created by old pipeline)
    op.execute(
        "UPDATE analysis_jobs "
        "SET analysis_config = analysis_config::jsonb - 'snapshot_id' "
        "|| jsonb_build_object('slice_id', (analysis_config->>'snapshot_id')::int) "
        "WHERE (analysis_config->>'snapshot_id') IS NOT NULL AND task_id IS NULL"
    )


def downgrade() -> None:
    # Reverse analysis_config JSON update
    op.execute(
        "UPDATE analysis_jobs "
        "SET analysis_config = analysis_config::jsonb - 'slice_id' "
        "|| jsonb_build_object('snapshot_id', (analysis_config->>'slice_id')::int) "
        "WHERE (analysis_config->>'slice_id') IS NOT NULL AND task_id IS NULL"
    )

    # Reverse analysis_type values
    op.execute(
        "UPDATE analysis_jobs "
        "SET analysis_type = 'project_snapshot_summary' "
        "WHERE analysis_type = 'project_slice_summary'"
    )

    # Rename indexes back
    op.execute(
        "ALTER INDEX IF EXISTS idx_project_slices_project "
        "RENAME TO idx_project_snapshots_project"
    )
    op.execute(
        "ALTER INDEX IF EXISTS idx_project_slices_created_at "
        "RENAME TO idx_project_snapshots_created_at"
    )

    # Rename table back
    op.rename_table("project_analysis_slices", "project_analysis_snapshots")
