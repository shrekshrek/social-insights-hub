"""fix_research_tasks_schema

1. 将 query 列重命名为 analysis_goal（与 API 层命名一致）
2. 删除 3 个重复索引：strategy_id / user_id / status 各有两个索引，
   保留 index=True 自动创建的 ix_research_tasks_* 系列，
   删除手动创建的 idx_research_task_* 系列。

Revision ID: fix_research_tasks_schema
Revises: add_progress_research_tasks
Create Date: 2026-04-13

"""

from typing import Sequence, Union

from alembic import op

revision: str = "fix_research_tasks_schema"
down_revision: Union[str, Sequence[str]] = "add_progress_research_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 列改名
    op.alter_column("research_tasks", "query", new_column_name="analysis_goal")

    # 2. 删除重复索引（保留 ix_research_tasks_* 系列）
    op.drop_index("idx_research_task_strategy", table_name="research_tasks")
    op.drop_index("idx_research_task_user", table_name="research_tasks")
    op.drop_index("idx_research_task_status", table_name="research_tasks")


def downgrade() -> None:
    # 恢复重复索引
    op.create_index("idx_research_task_status", "research_tasks", ["status"])
    op.create_index("idx_research_task_user", "research_tasks", ["user_id"])
    op.create_index("idx_research_task_strategy", "research_tasks", ["strategy_id"])

    # 列名回退
    op.alter_column("research_tasks", "analysis_goal", new_column_name="query")
