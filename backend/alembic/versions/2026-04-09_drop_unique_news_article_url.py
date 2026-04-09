"""drop unique constraint on news_articles.url

设计上同一 URL 在不同任务下各自独立存储（见 NewsArticle docstring），
原始迁移将 url 建为 unique index 与设计不符，改为普通 index。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-09

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_news_articles_url", table_name="news_articles")
    op.create_index(
        "ix_news_articles_url", "news_articles", ["url"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_news_articles_url", table_name="news_articles")
    op.create_index(
        "ix_news_articles_url", "news_articles", ["url"], unique=True
    )
