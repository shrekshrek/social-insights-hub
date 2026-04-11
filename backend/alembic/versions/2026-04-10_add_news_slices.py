"""add_news_slices

Revision ID: 94101c74fff0
Revises: d4e5f6a0b1c2
Create Date: 2026-04-10 16:56:42.854684

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '94101c74fff0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('news_slices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False, comment='切片名称'),
    sa.Column('monitor_id', sa.Integer(), nullable=False, comment='所属新闻监测项目'),
    sa.Column('included_task_ids', sa.JSON(), nullable=False, comment='参与合并的 NewsTask ID 列表'),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False, comment='pending | analyzing | completed | failed'),
    sa.Column('result_data', sa.JSON(), nullable=True, comment='insight 分析结果'),
    sa.Column('stats', sa.JSON(), nullable=True, comment='统计摘要（文章数/来源分布/情感分布/实体 Top N）'),
    sa.Column('error_message', sa.String(length=1000), nullable=True, comment='失败原因'),
    sa.Column('created_by', sa.Integer(), nullable=False, comment='创建者'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_news_slices_created_by_users')),
    sa.ForeignKeyConstraint(['monitor_id'], ['news_monitors.id'], name=op.f('fk_news_slices_monitor_id_news_monitors'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_news_slices'))
    )
    op.create_index('idx_news_slices_monitor', 'news_slices', ['monitor_id'], unique=False)
    op.create_index('idx_news_slices_created_at', 'news_slices', ['created_at'], unique=False)
    op.create_index(op.f('ix_news_slices_created_by'), 'news_slices', ['created_by'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_news_slices_created_by'), table_name='news_slices')
    op.drop_index('idx_news_slices_created_at', table_name='news_slices')
    op.drop_index('idx_news_slices_monitor', table_name='news_slices')
    op.drop_table('news_slices')
