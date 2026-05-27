"""add email_verified to users

Revision ID: 2026052701
Revises: 8f9417832101
Create Date: 2026-05-27 12:50:00.000000

幂等迁移：为支持邮箱验证（邀请制注册 + 管理员重置密码），
为 users 表新增 email_verified 列。

生产环境已通过手工 SQL 添加过此列，因此使用 IF NOT EXISTS
保证此迁移在线上/dev 都能幂等执行。
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2026052701"
down_revision: Union[str, Sequence[str], None] = "8f9417832101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Idempotently add email_verified column to users."""
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS email_verified BOOLEAN
        NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    """Drop email_verified column from users."""
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
