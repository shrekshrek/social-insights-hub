"""add news_articles table

Revision ID: e2f3g4h5i6j7
Revises: d1e2f3g4h5i6
Create Date: 2026-04-02

新增 news_articles 表，存储 SerpAPI 搜索文章元数据 + Crawl4AI 全文 + 逐篇轻量分析结果。
对标社媒的 social_posts 表。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3g4h5i6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), nullable=False),
        # 任务关联
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("news_tasks.id", ondelete="CASCADE"),
            nullable=False,
            comment="所属采集任务ID",
        ),
        # 文章元数据（SerpAPI 返回）
        sa.Column(
            "url", sa.String(2048), nullable=False, comment="文章链接（去重键）"
        ),
        sa.Column("title", sa.String(500), nullable=False, comment="文章标题"),
        sa.Column(
            "snippet", sa.Text(), nullable=True, comment="SerpAPI 返回的摘要片段"
        ),
        sa.Column(
            "source_name", sa.String(255), nullable=False, comment="来源媒体名称"
        ),
        sa.Column(
            "source_tier",
            sa.String(20),
            nullable=False,
            server_default="tier3",
            comment="来源等级: tier1/tier2/tier3",
        ),
        sa.Column("author", sa.String(255), nullable=True, comment="作者"),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="发布时间",
        ),
        sa.Column(
            "image_url", sa.String(2048), nullable=True, comment="配图链接"
        ),
        # Crawl4AI 全文
        sa.Column(
            "full_text",
            sa.Text(),
            nullable=True,
            comment="Crawl4AI 抓取的全文",
        ),
        # 逐篇轻量分析结果
        sa.Column(
            "relevance",
            sa.String(20),
            nullable=True,
            comment="与研究目标的相关程度: high/medium/low",
        ),
        sa.Column(
            "sentiment", sa.Float(), nullable=True, comment="情感分 -1 ~ 1"
        ),
        sa.Column(
            "article_type",
            sa.String(50),
            nullable=True,
            comment="文章类型: report/opinion/pr/analysis",
        ),
        sa.Column(
            "mentioned_entities",
            sa.JSON(),
            nullable=True,
            comment="提及的实体名单",
        ),
        sa.Column(
            "key_quotes", sa.JSON(), nullable=True, comment="关键引述"
        ),
        sa.Column("summary", sa.Text(), nullable=True, comment="一句话摘要"),
        # 原始数据
        sa.Column(
            "raw_data", sa.JSON(), nullable=True, comment="SerpAPI 原始响应"
        ),
        # 时间戳
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_articles_task_id", "news_articles", ["task_id"])
    op.create_index(
        "ix_news_articles_url", "news_articles", ["url"], unique=True
    )
    op.create_index(
        "ix_news_articles_source_tier", "news_articles", ["source_tier"]
    )
    op.create_index(
        "ix_news_articles_relevance", "news_articles", ["relevance"]
    )


def downgrade() -> None:
    op.drop_index("ix_news_articles_relevance", table_name="news_articles")
    op.drop_index("ix_news_articles_source_tier", table_name="news_articles")
    op.drop_index("ix_news_articles_url", table_name="news_articles")
    op.drop_index("ix_news_articles_task_id", table_name="news_articles")
    op.drop_table("news_articles")
