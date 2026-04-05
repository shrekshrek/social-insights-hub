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
    # 删除旧外键约束（使用数据库实际约束名）
    op.drop_constraint("fk_monitor_participants_monitor_id_monitors", "monitor_participants", type_="foreignkey")
    op.drop_constraint("fk_social_data_tasks_monitor_id_monitors", "social_data_tasks", type_="foreignkey")
    op.drop_constraint("fk_analysis_jobs_monitor_id_monitors", "analysis_jobs", type_="foreignkey")
    op.drop_constraint("fk_analysis_slices_monitor_id_monitors", "analysis_slices", type_="foreignkey")
    op.drop_constraint("fk_strategies_monitor_id_monitors", "strategies", type_="foreignkey")

    # 重命名表
    op.rename_table("monitors", "social_monitors")

    # 重建外键约束（指向新表名）
    op.create_foreign_key(None, "monitor_participants", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "social_data_tasks", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "analysis_jobs", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "analysis_slices", "social_monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(None, "strategies", "social_monitors", ["social_monitor_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(None, "strategies", type_="foreignkey")
    op.drop_constraint(None, "analysis_slices", type_="foreignkey")
    op.drop_constraint(None, "analysis_jobs", type_="foreignkey")
    op.drop_constraint(None, "social_data_tasks", type_="foreignkey")
    op.drop_constraint(None, "monitor_participants", type_="foreignkey")

    op.rename_table("social_monitors", "monitors")

    op.create_foreign_key("fk_strategies_monitor_id_monitors", "strategies", "monitors", ["social_monitor_id"], ["id"])
    op.create_foreign_key("fk_analysis_slices_monitor_id_monitors", "analysis_slices", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_analysis_jobs_monitor_id_monitors", "analysis_jobs", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_social_data_tasks_monitor_id_monitors", "social_data_tasks", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_monitor_participants_monitor_id_monitors", "monitor_participants", "monitors", ["monitor_id"], ["id"], ondelete="CASCADE")
