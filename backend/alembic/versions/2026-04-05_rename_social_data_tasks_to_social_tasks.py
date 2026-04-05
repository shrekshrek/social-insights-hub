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
    # 删除旧外键约束（使用数据库实际约束名）
    op.drop_constraint("fk_social_posts_task_id_social_data_tasks", "social_posts", type_="foreignkey")
    op.drop_constraint("fk_social_comments_task_id_social_data_tasks", "social_comments", type_="foreignkey")
    op.drop_constraint("fk_post_analysis_task_id_social_data_tasks", "post_analysis", type_="foreignkey")
    op.drop_constraint("fk_analysis_jobs_task_id_social_data_tasks", "analysis_jobs", type_="foreignkey")

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

    op.create_foreign_key("fk_analysis_jobs_task_id_social_data_tasks", "analysis_jobs", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_post_analysis_task_id_social_data_tasks", "post_analysis", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_social_comments_task_id_social_data_tasks", "social_comments", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_social_posts_task_id_social_data_tasks", "social_posts", "social_data_tasks", ["task_id"], ["id"], ondelete="CASCADE")
