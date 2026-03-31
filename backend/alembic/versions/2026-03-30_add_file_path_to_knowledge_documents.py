"""add file_path to knowledge_documents

Revision ID: b30499e4bd19
Revises: 82000f2fde50
Create Date: 2026-03-30 19:07:09.679786

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b30499e4bd19'
down_revision: Union[str, Sequence[str], None] = '82000f2fde50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'knowledge_documents',
        sa.Column('file_path', sa.Text(), nullable=True, comment='服务器本地文件路径，用于查看原文'),
    )


def downgrade() -> None:
    op.drop_column('knowledge_documents', 'file_path')
