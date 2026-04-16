"""add_operation_fields_to_audit_logs

Revision ID: add_operation_to_audit_logs
Revises: add_profile_name_research_tasks
Create Date: 2026-04-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_operation_to_audit_logs"
down_revision: Union[str, Sequence[str]] = "add_profile_name_research_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("operation", sa.String(length=100), nullable=True, comment="友好操作名（来自 route.summary）"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("endpoint", sa.String(length=100), nullable=True, comment="端点函数名（来自 route.name）"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("path_template", sa.String(length=500), nullable=True, comment="路径模板（来自 route.path，用于按接口聚合）"),
    )
    op.create_index("ix_audit_logs_endpoint", "audit_logs", ["endpoint"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_endpoint", table_name="audit_logs")
    op.drop_column("audit_logs", "path_template")
    op.drop_column("audit_logs", "endpoint")
    op.drop_column("audit_logs", "operation")
