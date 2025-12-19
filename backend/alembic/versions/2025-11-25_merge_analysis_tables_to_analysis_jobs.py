"""merge_analysis_tables_to_analysis_jobs

合并 task_analysis_results 和 project_analysis_results 表为 analysis_jobs 表。

Revision ID: f1a2b3c4d5e6
Revises: e0668138bae4
Create Date: 2025-11-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e0668138bae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """合并分析表为 analysis_jobs"""

    # 1. 创建新的 analysis_jobs 表
    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False, comment='关联的项目ID（必填）'),
        sa.Column('task_id', sa.Integer(), nullable=True, comment='关联的数据任务ID（任务级分析时填写，项目级分析时为空）'),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='执行分析的用户ID'),
        sa.Column('analysis_type', sa.String(length=50), nullable=False, comment='分析类型'),
        sa.Column('analysis_config', sa.JSON(), nullable=True, comment='分析配置参数'),
        sa.Column('source_task_ids', sa.JSON(), nullable=True, comment='源任务ID列表'),
        sa.Column('source_count', sa.Integer(), nullable=False, default=0, comment='源数据数量'),
        sa.Column('analyzed_count', sa.Integer(), nullable=False, default=0, comment='成功分析数量'),
        sa.Column('failed_count', sa.Integer(), nullable=False, default=0, comment='失败数量'),
        sa.Column('result_data', sa.JSON(), nullable=True, comment='聚合统计结果'),
        sa.Column('analysis_summary', sa.Text(), nullable=True, comment='分析摘要'),
        sa.Column('celery_task_id', sa.String(length=255), nullable=False, comment='Celery任务ID'),
        sa.Column('status', sa.String(length=50), nullable=False, default='pending', comment='状态'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True, comment='任务开始时间'),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True, comment='任务完成时间'),
        sa.Column('processing_time', sa.Integer(), nullable=True, comment='处理耗时（秒）'),
        sa.Column('token_usage', sa.JSON(), nullable=True, comment='Token使用统计'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['social_projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['social_data_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. 创建索引
    op.create_index('idx_analysis_job_project', 'analysis_jobs', ['project_id'])
    op.create_index('idx_analysis_job_task', 'analysis_jobs', ['task_id'])
    op.create_index('idx_analysis_job_type_status', 'analysis_jobs', ['analysis_type', 'status'])
    op.create_index('idx_analysis_job_created_at', 'analysis_jobs', ['created_at'])
    op.create_index('idx_analysis_job_user', 'analysis_jobs', ['user_id'])
    op.create_index('ix_analysis_jobs_celery_task_id', 'analysis_jobs', ['celery_task_id'], unique=True)

    # 3. 迁移 task_analysis_results 数据到 analysis_jobs
    # 需要从 task 获取 project_id，并添加 user_id
    bind = op.get_bind()

    # 检查 task_analysis_results 表是否存在
    inspector = sa.inspect(bind)
    if 'task_analysis_results' in inspector.get_table_names():
        # 迁移任务级分析数据
        bind.execute(sa.text("""
            INSERT INTO analysis_jobs (
                project_id, task_id, user_id, analysis_type,
                source_count, analyzed_count, failed_count,
                result_data, analysis_summary, celery_task_id, status,
                started_at, completed_at, processing_time, token_usage, error_message,
                created_at, updated_at
            )
            SELECT
                t.project_id,
                tar.task_id,
                COALESCE(t.creator_id, 1) as user_id,
                tar.analysis_type,
                tar.source_count,
                tar.analyzed_count,
                tar.failed_count,
                tar.result_data,
                tar.analysis_summary,
                tar.celery_task_id,
                tar.status,
                tar.started_at,
                tar.completed_at,
                tar.processing_time,
                tar.token_usage,
                tar.error_message,
                tar.created_at,
                tar.updated_at
            FROM task_analysis_results tar
            JOIN social_data_tasks t ON t.id = tar.task_id
        """))

    # 检查 project_analysis_results 表是否存在
    if 'project_analysis_results' in inspector.get_table_names():
        # 迁移项目级分析数据
        bind.execute(sa.text("""
            INSERT INTO analysis_jobs (
                project_id, task_id, user_id, analysis_type,
                analysis_config, source_task_ids, source_count,
                result_data, analysis_summary, celery_task_id, status,
                completed_at, processing_time, token_usage, error_message,
                created_at, updated_at
            )
            SELECT
                par.project_id,
                NULL as task_id,
                par.user_id,
                par.analysis_type,
                par.analysis_config,
                par.source_task_ids,
                par.source_data_count,
                par.result_data,
                par.analysis_summary,
                par.celery_task_id,
                par.status,
                par.completed_at,
                par.processing_time,
                par.token_usage,
                par.error_message,
                par.created_at,
                par.updated_at
            FROM project_analysis_results par
        """))

    # 4. 删除旧表
    if 'task_analysis_results' in inspector.get_table_names():
        op.drop_table('task_analysis_results')

    if 'project_analysis_results' in inspector.get_table_names():
        op.drop_table('project_analysis_results')


def downgrade() -> None:
    """恢复原来的两张表"""

    # 1. 重新创建 task_analysis_results 表
    op.create_table(
        'task_analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=False),
        sa.Column('result_data', sa.JSON(), nullable=True),
        sa.Column('analysis_summary', sa.Text(), nullable=True),
        sa.Column('source_count', sa.Integer(), default=0),
        sa.Column('analyzed_count', sa.Integer(), default=0),
        sa.Column('failed_count', sa.Integer(), default=0),
        sa.Column('celery_task_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_time', sa.Integer(), nullable=True),
        sa.Column('token_usage', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['task_id'], ['social_data_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. 重新创建 project_analysis_results 表
    op.create_table(
        'project_analysis_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=False),
        sa.Column('analysis_config', sa.JSON(), nullable=True),
        sa.Column('source_task_ids', sa.JSON(), nullable=True),
        sa.Column('source_data_count', sa.Integer(), default=0),
        sa.Column('result_data', sa.JSON(), nullable=True),
        sa.Column('analysis_summary', sa.Text(), nullable=True),
        sa.Column('celery_task_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, default='pending'),
        sa.Column('processing_time', sa.Integer(), nullable=True),
        sa.Column('token_usage', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['project_id'], ['social_projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. 迁移数据回去
    bind = op.get_bind()

    # 迁移任务级分析数据
    bind.execute(sa.text("""
        INSERT INTO task_analysis_results (
            task_id, analysis_type, result_data, analysis_summary,
            source_count, analyzed_count, failed_count,
            celery_task_id, status, started_at, completed_at,
            processing_time, token_usage, error_message,
            created_at, updated_at
        )
        SELECT
            task_id, analysis_type, result_data, analysis_summary,
            source_count, analyzed_count, failed_count,
            celery_task_id, status, started_at, completed_at,
            processing_time, token_usage, error_message,
            created_at, updated_at
        FROM analysis_jobs
        WHERE task_id IS NOT NULL
    """))

    # 迁移项目级分析数据
    bind.execute(sa.text("""
        INSERT INTO project_analysis_results (
            project_id, user_id, analysis_type, analysis_config, source_task_ids,
            source_data_count, result_data, analysis_summary,
            celery_task_id, status, processing_time, token_usage, error_message,
            created_at, completed_at, updated_at
        )
        SELECT
            project_id, user_id, analysis_type, analysis_config, source_task_ids,
            source_count, result_data, analysis_summary,
            celery_task_id, status, processing_time, token_usage, error_message,
            created_at, completed_at, updated_at
        FROM analysis_jobs
        WHERE task_id IS NULL
    """))

    # 4. 删除 analysis_jobs 表
    op.drop_table('analysis_jobs')
