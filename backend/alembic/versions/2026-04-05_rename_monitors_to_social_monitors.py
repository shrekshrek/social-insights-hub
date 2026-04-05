"""rename monitors to social_monitors

Revision ID: a1b2c3d4e5f6
Revises: f3g4h5i6j7k8
Create Date: 2026-04-05

"""

from typing import Sequence, Union
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3g4h5i6j7k8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 受影响的外键：
#   monitor_participants.monitor_id -> monitors.id
#   social_data_tasks.monitor_id   -> monitors.id
#   analysis_jobs.monitor_id       -> monitors.id
#   analysis_slices.monitor_id     -> monitors.id
#   strategies.monitor_id          -> monitors.id


def upgrade() -> None:
    # 删除旧外键约束
    op.drop_constraint("monitor_participants_monitor_id_fkey", "monitor_participants", type_="foreignkey")
    op.drop_constraint("social_data_tasks_monitor_id_fkey", "social_data_tasks", type_="foreignkey")
    op.drop_constraint("analysis_jobs_monitor_id_fkey", "analysis_jobs", type_="foreignkey")
    op.drop_constraint("analysis_slices_monitor_id_fkey", "analysis_slices", type_="foreignkey")
    op.drop_constraint("strategies_monitor_id_fkey", "strategies", type_="foreignkey")

    # 重命名表
    op.rename_table("monitors", "social_monitors")

    # 重建外键约束（指向新表名）
    op.create_foreign_key(None, "monitor_participants", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "social_data_tasks", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "analysis_jobs", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "analysis_slices", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "strategies", "social_monitors", ["monitor_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(None, "strategies", type_="foreignkey")
    op.drop_constraint(None, "analysis_slices", type_="foreignkey")
    op.drop_constraint(None, "analysis_jobs", type_="foreignkey")
    op.drop_constraint(None, "social_data_tasks", type_="foreignkey")
    op.drop_constraint(None, "monitor_participants", type_="foreignkey")

    op.rename_table("social_monitors", "monitors")

    op.create_foreign_key("strategies_monitor_id_fkey", "strategies", "monitors", ["monitor_id"], ["id"])
    op.create_foreign_key("analysis_slices_monitor_id_fkey", "analysis_slices", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("analysis_jobs_monitor_id_fkey", "analysis_jobs", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("social_data_tasks_monitor_id_fkey", "social_data_tasks", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("monitor_participants_monitor_id_fkey", "monitor_participants", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
