"""rename owner_id to user_id in social_monitors and news_monitors

Revision ID: rename_owner_id_monitors
Revises: fix_research_tasks_schema
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op

revision: str = "rename_owner_id_monitors"
down_revision: Union[str, Sequence[str]] = "fix_research_tasks_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # social_monitors: rename owner_id → user_id
    op.execute("ALTER TABLE social_monitors RENAME COLUMN owner_id TO user_id")
    op.execute("ALTER INDEX IF EXISTS ix_monitors_owner_id RENAME TO ix_social_monitors_user_id")

    # news_monitors: rename owner_id → user_id
    op.execute("ALTER TABLE news_monitors RENAME COLUMN owner_id TO user_id")
    op.execute("ALTER INDEX IF EXISTS ix_news_monitors_owner_id RENAME TO ix_news_monitors_user_id")


def downgrade() -> None:
    op.execute("ALTER TABLE social_monitors RENAME COLUMN user_id TO owner_id")
    op.execute("ALTER INDEX IF EXISTS ix_social_monitors_user_id RENAME TO ix_monitors_owner_id")

    op.execute("ALTER TABLE news_monitors RENAME COLUMN user_id TO owner_id")
    op.execute("ALTER INDEX IF EXISTS ix_news_monitors_user_id RENAME TO ix_news_monitors_owner_id")
