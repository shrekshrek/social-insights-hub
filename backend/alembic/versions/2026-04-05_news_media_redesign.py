"""news_media redesign: remove search_provider, add search_source and aggregated_result

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-04-05

移除 news_monitors.search_provider 和 news_tasks.search_provider（旧 SerpAPI 方案产物）。
新增 news_articles.search_source（baidu/duckduckgo）。
新增 news_monitors.aggregated_result（跨任务叙事聚合结果）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, Sequence[str], None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # news_monitors: 删除 search_provider，新增 aggregated_result
    op.drop_column("news_monitors", "search_provider")
    op.add_column(
        "news_monitors",
        sa.Column("aggregated_result", sa.JSON(), nullable=True),
    )

    # news_tasks: 删除 search_provider
    op.drop_column("news_tasks", "search_provider")

    # news_articles: 新增 search_source
    op.add_column(
        "news_articles",
        sa.Column(
            "search_source",
            sa.String(20),
            nullable=False,
            server_default="baidu",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_articles", "search_source")
    op.drop_column("news_monitors", "aggregated_result")
    op.add_column(
        "news_monitors",
        sa.Column(
            "search_provider",
            sa.String(50),
            nullable=False,
            server_default="serpapi_baidu",
        ),
    )
    op.add_column(
        "news_tasks",
        sa.Column(
            "search_provider",
            sa.String(50),
            nullable=False,
            server_default="serpapi_baidu",
        ),
    )
