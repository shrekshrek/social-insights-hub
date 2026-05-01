"""add research_task_participants association table

Revision ID: f1e96931e5e9
Revises: backfill_slice_status_stage2
Create Date: 2026-05-01 07:24:06.451398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1e96931e5e9'
down_revision: Union[str, Sequence[str], None] = 'backfill_slice_status_stage2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'research_task_participants',
        sa.Column('research_task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['research_task_id'],
            ['research_tasks.id'],
            name=op.f('fk_research_task_participants_research_task_id_research_tasks'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_research_task_participants_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint(
            'research_task_id',
            'user_id',
            name=op.f('pk_research_task_participants'),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('research_task_participants')
