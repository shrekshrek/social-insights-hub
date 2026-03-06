"""rename analysis_type project_slice_summary to monitor_slice_summary

Revision ID: 20260306_analysis_type_rename
Revises: 4a80e776ebe4
Create Date: 2026-03-06

Data migration: UPDATE analysis_jobs SET analysis_type = 'monitor_slice_summary'
WHERE analysis_type = 'project_slice_summary'
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260306_analysis_type_rename"
down_revision: Union[str, Sequence[str], None] = "4a80e776ebe4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE analysis_jobs SET analysis_type = 'monitor_slice_summary' "
        "WHERE analysis_type = 'project_slice_summary'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE analysis_jobs SET analysis_type = 'project_slice_summary' "
        "WHERE analysis_type = 'monitor_slice_summary'"
    )
