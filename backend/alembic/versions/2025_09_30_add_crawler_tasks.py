"""add crawler tasks tables

Revision ID: 2025_09_30_001
Revises: aa99cf3f13cf
Create Date: 2025-09-30 19:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2025_09_30_001'
down_revision: Union[str, None] = 'aa99cf3f13cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建爬虫任务表
    op.create_table(
        'crawler_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, comment='任务名称'),
        sa.Column('platform', sa.Enum('xhs', 'weibo', 'douyin', 'kuaishou', 'bilibili', 'tieba', 'zhihu', name='platformtype'), nullable=False, comment='爬取平台'),
        sa.Column('crawler_type', sa.Enum('search', 'detail', 'creator', 'homefeed', name='crawlertype'), nullable=False, comment='爬取模式'),
        sa.Column('status', sa.Enum('pending', 'running', 'paused', 'completed', 'failed', 'cancelled', name='taskstatus'), nullable=False, comment='任务状态'),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False, comment='爬取配置(关键词、URL、数量等)'),
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0', comment='进度(0-100)'),
        sa.Column('crawled_count', sa.Integer(), nullable=True, server_default='0', comment='已爬取数量'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('started_at', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('completed_at', sa.DateTime(), nullable=True, comment='完成时间'),
        sa.Column('checkpoint_id', sa.String(length=255), nullable=True, comment='检查点ID'),
        sa.Column('checkpoint_data', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='检查点数据'),
        sa.Column('created_by', sa.Integer(), nullable=True, comment='创建人ID'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('progress >= 0 AND progress <= 100', name='check_progress_range'),
        comment='爬虫任务表'
    )
    op.create_index(op.f('ix_crawler_tasks_platform'), 'crawler_tasks', ['platform'], unique=False)
    op.create_index(op.f('ix_crawler_tasks_status'), 'crawler_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_crawler_tasks_created_by'), 'crawler_tasks', ['created_by'], unique=False)

    # 创建任务日志表
    op.create_table(
        'crawler_task_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False, comment='日志级别: INFO/WARNING/ERROR'),
        sa.Column('message', sa.Text(), nullable=False, comment='日志内容'),
        sa.Column('detail', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='详细信息(JSON)'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'), comment='记录时间'),
        sa.ForeignKeyConstraint(['task_id'], ['crawler_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='任务执行日志表'
    )
    op.create_index(op.f('ix_crawler_task_logs_task_id'), 'crawler_task_logs', ['task_id'], unique=False)
    op.create_index(op.f('ix_crawler_task_logs_created_at'), 'crawler_task_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_crawler_task_logs_created_at'), table_name='crawler_task_logs')
    op.drop_index(op.f('ix_crawler_task_logs_task_id'), table_name='crawler_task_logs')
    op.drop_table('crawler_task_logs')

    op.drop_index(op.f('ix_crawler_tasks_created_by'), table_name='crawler_tasks')
    op.drop_index(op.f('ix_crawler_tasks_status'), table_name='crawler_tasks')
    op.drop_index(op.f('ix_crawler_tasks_platform'), table_name='crawler_tasks')
    op.drop_table('crawler_tasks')

    # 删除枚举类型
    op.execute('DROP TYPE IF EXISTS taskstatus')
    op.execute('DROP TYPE IF EXISTS crawlertype')
    op.execute('DROP TYPE IF EXISTS platformtype')