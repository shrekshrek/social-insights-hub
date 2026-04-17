"""simplify_audit_logs_remove_http_fields

删除 audit_logs 表中的 HTTP 调试字段：
- endpoint（端点函数名）
- path_template（路径模板）
- http_method（HTTP 方法，action 字段已表达语义）
- user_agent（浏览器标识，对操作日志无意义）

Revision ID: simplify_audit_logs_http_fields
Revises: 05361f53c559
Create Date: 2026-04-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "simplify_audit_logs_http_fields"
down_revision: Union[str, Sequence[str]] = "05361f53c559"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_audit_logs_endpoint", table_name="audit_logs", if_exists=True)
    op.drop_column("audit_logs", "endpoint")
    op.drop_column("audit_logs", "path_template")
    op.drop_column("audit_logs", "http_method")
    op.drop_column("audit_logs", "user_agent")


def downgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("user_agent", sa.Text(), nullable=True, comment="User-Agent"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("http_method", sa.String(length=10), nullable=True, comment="HTTP方法：POST/PUT/PATCH/DELETE"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("path_template", sa.String(length=500), nullable=True, comment="路径模板"),
    )
    op.add_column(
        "audit_logs",
        sa.Column("endpoint", sa.String(length=100), nullable=True, comment="端点函数名"),
    )
    op.create_index("ix_audit_logs_endpoint", "audit_logs", ["endpoint"])
