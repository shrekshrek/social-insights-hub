"""refactor analysis_jobs: rename monitor_id/task_id, add news FK fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-05

Changes:
- analysis_jobs.monitor_id (NOT NULL FK → social_monitors) → social_monitor_id (nullable)
- analysis_jobs.task_id (nullable FK → social_tasks) → social_task_id (nullable)
- Add analysis_jobs.news_monitor_id (nullable FK → news_monitors)
- Add analysis_jobs.news_task_id (nullable FK → news_tasks)
- Update indexes accordingly
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删除旧外键约束
    op.drop_constraint(
        "fk_analysis_jobs_monitor_id_social_monitors", "analysis_jobs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_analysis_jobs_task_id_social_tasks", "analysis_jobs", type_="foreignkey"
    )

    # 2. 删除旧索引
    op.drop_index("idx_analysis_job_project", table_name="analysis_jobs")
    op.drop_index("idx_analysis_job_task", table_name="analysis_jobs")

    # 3. 重命名列 monitor_id → social_monitor_id（同时改为 nullable）
    op.alter_column(
        "analysis_jobs",
        "monitor_id",
        new_column_name="social_monitor_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 4. 重命名列 task_id → social_task_id
    op.alter_column(
        "analysis_jobs",
        "task_id",
        new_column_name="social_task_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 5. 新增 news_monitor_id 和 news_task_id
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "news_monitor_id",
            sa.Integer(),
            sa.ForeignKey("news_monitors.id", ondelete="CASCADE", name="fk_analysis_jobs_news_monitor_id_news_monitors"),
            nullable=True,
            comment="关联的新闻监测项目ID",
        ),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "news_task_id",
            sa.Integer(),
            sa.ForeignKey("news_tasks.id", ondelete="CASCADE", name="fk_analysis_jobs_news_task_id_news_tasks"),
            nullable=True,
            comment="关联的新闻采集任务ID",
        ),
    )

    # 6. 重建外键（新名称）
    op.create_foreign_key(
        "fk_analysis_jobs_social_monitor_id_social_monitors",
        "analysis_jobs",
        "social_monitors",
        ["social_monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_analysis_jobs_social_task_id_social_tasks",
        "analysis_jobs",
        "social_tasks",
        ["social_task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 7. 重建索引
    op.create_index("idx_analysis_job_social_monitor", "analysis_jobs", ["social_monitor_id"])
    op.create_index("idx_analysis_job_social_task", "analysis_jobs", ["social_task_id"])
    op.create_index("idx_analysis_job_news_monitor", "analysis_jobs", ["news_monitor_id"])
    op.create_index("idx_analysis_job_news_task", "analysis_jobs", ["news_task_id"])


def downgrade() -> None:
    # 删除新增索引
    op.drop_index("idx_analysis_job_news_task", table_name="analysis_jobs")
    op.drop_index("idx_analysis_job_news_monitor", table_name="analysis_jobs")
    op.drop_index("idx_analysis_job_social_task", table_name="analysis_jobs")
    op.drop_index("idx_analysis_job_social_monitor", table_name="analysis_jobs")

    # 删除新增外键
    op.drop_constraint(
        "fk_analysis_jobs_social_task_id_social_tasks", "analysis_jobs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_analysis_jobs_social_monitor_id_social_monitors", "analysis_jobs", type_="foreignkey"
    )

    # 删除新增列
    op.drop_column("analysis_jobs", "news_task_id")
    op.drop_column("analysis_jobs", "news_monitor_id")

    # 重命名回原名
    op.alter_column(
        "analysis_jobs",
        "social_task_id",
        new_column_name="task_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "analysis_jobs",
        "social_monitor_id",
        new_column_name="monitor_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 重建原外键
    op.create_foreign_key(
        "fk_analysis_jobs_monitor_id_social_monitors",
        "analysis_jobs",
        "social_monitors",
        ["monitor_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_analysis_jobs_task_id_social_tasks",
        "analysis_jobs",
        "social_tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 重建原索引
    op.create_index("idx_analysis_job_project", "analysis_jobs", ["monitor_id"])
    op.create_index("idx_analysis_job_task", "analysis_jobs", ["task_id"])
