"""add_research_tasks_table

新增 research_tasks 表，支持 Research Agent 模块（独立研究 + 策略渠道）。

Revision ID: a0b1c2d3e4f5
Revises: f6a1b2c3d4e5, d4e5f6a0b1c2
Create Date: 2026-04-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str]] = ("f6a1b2c3d4e5", "d4e5f6a0b1c2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False, comment="研究主题"),
        sa.Column(
            "research_questions", sa.JSON(), nullable=True, comment="研究问题列表"
        ),
        sa.Column(
            "search_config",
            sa.JSON(),
            nullable=True,
            comment="research_angles, focus_domains 等搜索配置",
        ),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
            comment="关联策略（策略模式下非空）",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
            comment="创建者",
        ),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            comment="关联 AnalysisJob（token/cost 追踪）",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            index=True,
            comment="pending / running / completed / failed",
        ),
        sa.Column(
            "error_message", sa.Text(), nullable=True, comment="失败原因"
        ),
        sa.Column(
            "result_data",
            sa.JSON(),
            nullable=True,
            comment="synthesis + findings + sources",
        ),
        sa.Column(
            "stats",
            sa.JSON(),
            nullable=True,
            comment="rounds, documents_analyzed 等统计",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_index(
        "idx_research_task_strategy", "research_tasks", ["strategy_id"]
    )
    op.create_index(
        "idx_research_task_status", "research_tasks", ["status"]
    )
    op.create_index(
        "idx_research_task_user", "research_tasks", ["user_id"]
    )
    op.create_index(
        "idx_research_task_created_at", "research_tasks", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_research_task_created_at", table_name="research_tasks")
    op.drop_index("idx_research_task_user", table_name="research_tasks")
    op.drop_index("idx_research_task_status", table_name="research_tasks")
    op.drop_index("idx_research_task_strategy", table_name="research_tasks")
    op.drop_table("research_tasks")
