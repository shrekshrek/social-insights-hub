"""add email_verified to user

Revision ID: a1b2c3d4e5f6
Revises: 8f9417832101
Create Date: 2026-05-27 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'ee1234567890'
down_revision: Union[str, None] = '8f9417832101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'email_verified',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        )
    )


def downgrade() -> None:
    op.drop_column('users', 'email_verified')
