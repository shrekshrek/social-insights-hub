"""add_oauth_fields_to_users

Revision ID: ad108e1b5e36
Revises: simplify_audit_logs_http_fields
Create Date: 2026-04-18 14:11:12.865119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad108e1b5e36'
down_revision: Union[str, Sequence[str], None] = 'simplify_audit_logs_http_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add OAuth fields to users table for Feishu login support."""
    op.add_column('users', sa.Column('oauth_provider', sa.String(length=20), nullable=True, comment='OAuth provider: feishu'))
    op.add_column('users', sa.Column('oauth_open_id', sa.String(length=128), nullable=True, comment='OAuth provider open_id'))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True, comment='User avatar URL from OAuth provider'))
    op.alter_column('users', 'hashed_password',
               existing_type=sa.VARCHAR(),
               nullable=True)
    op.create_index(op.f('ix_users_oauth_open_id'), 'users', ['oauth_open_id'], unique=True)


def downgrade() -> None:
    """Remove OAuth fields from users table."""
    op.drop_index(op.f('ix_users_oauth_open_id'), table_name='users')
    op.alter_column('users', 'hashed_password',
               existing_type=sa.VARCHAR(),
               nullable=False)
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'oauth_open_id')
    op.drop_column('users', 'oauth_provider')
