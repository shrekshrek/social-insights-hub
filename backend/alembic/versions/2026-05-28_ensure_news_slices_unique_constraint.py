"""ensure (monitor_id, name) unique constraint on news_slices

Revision ID: 2026052802
Revises: 2026052801
Create Date: 2026-05-28 09:30:00.000000

补丁迁移：commit f663a55 把 news_slices 的约束直接塞进了已存在的 2026052801
revision 文件，而非另起 revision。任何在 commit 2ee9c98（只含 social_slices
约束）后跑过 alembic upgrade 的环境，再拉 f663a55 时 alembic 已记录 2026052801
完成，news_slices 部分永远不会跑。

本迁移幂等地补加 news_slices 约束：如果约束已经存在（生产从 f663a55 直接部署
的情况）就跳过；不存在（生产先部署 2ee9c98 又部署 f663a55 的情况）就补上。
"""

from alembic import op


# revision identifiers, used by Alembic
revision = "2026052802"
down_revision = "2026052801"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 用 DO 块 + pg_constraint 查询实现幂等。PostgreSQL 没有 ADD CONSTRAINT IF NOT EXISTS。
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_news_slices_monitor_name'
            ) THEN
                -- 先删除重复行（保留每组 monitor_id+name 中 id 最小的那条）
                DELETE FROM news_slices
                WHERE id NOT IN (
                    SELECT MIN(id) FROM news_slices GROUP BY monitor_id, name
                );

                ALTER TABLE news_slices
                ADD CONSTRAINT uq_news_slices_monitor_name
                UNIQUE (monitor_id, name);
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE news_slices
        DROP CONSTRAINT IF EXISTS uq_news_slices_monitor_name;
        """
    )
