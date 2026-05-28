"""add unique constraint (monitor_id, name) to social_slices

Revision ID: 2026052801
Revises: 2026052701
Create Date: 2026-05-28 08:00:00.000000

问题背景：
  uvicorn --workers 4 时，多进程各自拥有独立的内存锁 _slice_creation_in_progress，
  并发轮询/APScheduler 触发建切片时，4 个进程同时通过内存锁检查，
  导致同名切片被创建 4 份（#6/#7/#8/#9），且 pipeline 未正确启动。

修复方案：
  在 DB 层添加 (monitor_id, name) 唯一约束，并发时第 2~4 个 INSERT 抛 IntegrityError，
  _create_auto_slices 捕获后幂等跳过，只有第一个 INSERT 成功。
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "2026052801"
down_revision = "2026052701"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 先删除重复行（保留每组 monitor_id+name 中 id 最小的那条）
    op.execute(
        """
        DELETE FROM social_slices
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM social_slices
            GROUP BY monitor_id, name
        )
        """
    )

    # 添加唯一约束（name 可为 NULL，NULL 不参与唯一校验，符合 SQL 标准）
    op.create_unique_constraint(
        "uq_social_slices_monitor_name",
        "social_slices",
        ["monitor_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_social_slices_monitor_name",
        "social_slices",
        type_="unique",
    )
