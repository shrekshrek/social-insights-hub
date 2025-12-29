"""add_project_analysis_snapshots

新增项目级“手动合并分析快照”表，用于保存多任务合并后的结果（不属于 LLM 分析任务流水）。

Revision ID: k1a2b3c4d5e6
Revises: j5e6f7g8h9i0
Create Date: 2025-12-17 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "j5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_analysis_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False, comment="关联的项目ID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="创建快照的用户ID"),
        sa.Column(
            "included_task_ids",
            sa.JSON(),
            nullable=False,
            comment="参与合并的任务ID列表",
        ),
        sa.Column("result_data", sa.JSON(), nullable=False, comment="快照结果数据"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["social_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_project_snapshots_project", "project_analysis_snapshots", ["project_id"]
    )
    op.create_index(
        "idx_project_snapshots_created_at", "project_analysis_snapshots", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "idx_project_snapshots_created_at", table_name="project_analysis_snapshots"
    )
    op.drop_index(
        "idx_project_snapshots_project", table_name="project_analysis_snapshots"
    )
    op.drop_table("project_analysis_snapshots")
