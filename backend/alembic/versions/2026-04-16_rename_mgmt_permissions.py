"""rename user_mgmt/role_mgmt/perm_mgmt permissions to user/role/permission access

Revision ID: rename_mgmt_permissions
Revises: rename_kb_processing_status
Create Date: 2026-04-16

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "rename_mgmt_permissions"
down_revision: Union[str, Sequence[str]] = "rename_kb_processing_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE permissions SET target = 'user'
        WHERE target = 'user_mgmt' AND action = 'access'
    """))
    conn.execute(text("""
        UPDATE permissions SET target = 'role'
        WHERE target = 'role_mgmt' AND action = 'access'
    """))
    conn.execute(text("""
        UPDATE permissions SET target = 'permission'
        WHERE target = 'perm_mgmt' AND action = 'access'
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("""
        UPDATE permissions SET target = 'user_mgmt'
        WHERE target = 'user' AND action = 'access'
    """))
    conn.execute(text("""
        UPDATE permissions SET target = 'role_mgmt'
        WHERE target = 'role' AND action = 'access'
    """))
    conn.execute(text("""
        UPDATE permissions SET target = 'perm_mgmt'
        WHERE target = 'permission' AND action = 'access'
    """))
