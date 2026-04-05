"""rename social_data_tasks to social_tasks

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 受影响的外键：
#   social_posts.task_id      -> social_data_tasks.id
#   social_comments.task_id   -> social_data_tasks.id
#   post_analysis.task_id     -> social_data_tasks.id
#   analysis_jobs.task_id     -> social_data_tasks.id


def upgrade() -> None:
    op.drop_constraint("social_posts_task_id_fkey", "social_posts", type_="foreignkey")
    op.drop_constraint("social_comments_task_id_fkey", "social_comments", type_="foreignkey")
    op.drop_constraint("post_analysis_task_id_fkey", "post_analysis", type_="foreignkey")
    op.drop_constraint("analysis_jobs_task_id_fkey", "analysis_jobs", type_="foreignkey")

    op.rename_table("social_data_tasks", "social_tasks")

    op.create_foreign_key(None, "social_posts", "social_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "social_comments", "social_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "post_analysis", "social_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "analysis_jobs", "social_tasks", ["task_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint(None, "analysis_jobs", type_="foreignkey")
    op.drop_constraint(None, "post_analysis", type_="foreignkey")
    op.drop_constraint(None, "social_comments", type_="foreignkey")
    op.drop_constraint(None, "social_posts", type_="foreignkey")

    op.rename_table("social_tasks", "social_data_tasks")

    op.create_foreign_key("analysis_jobs_task_id_fkey", "analysis_jobs", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("post_analysis_task_id_fkey", "post_analysis", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("social_comments_task_id_fkey", "social_comments", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("social_posts_task_id_fkey", "social_posts", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
