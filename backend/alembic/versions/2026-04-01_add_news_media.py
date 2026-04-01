"""add news_media module

Revision ID: d1e2f3g4h5i6
Revises: c1a2b3d4e5f6
Create Date: 2026-04-01

Phase 1: 新建 news_media 模块，接入 SerpAPI Baidu News + Crawl4AI。
新闻渠道作为策略流程的第二条采集通道。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3g4h5i6"
down_revision: Union[str, Sequence[str], None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 创建 news_monitors 表
    op.create_table(
        "news_monitors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="监测项目名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="项目描述"),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            comment="创建者用户ID",
        ),
        sa.Column(
            "search_provider",
            sa.String(50),
            nullable=False,
            server_default="serpapi_baidu",
            comment="搜索提供商",
        ),
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
    op.create_index("ix_news_monitors_owner_id", "news_monitors", ["owner_id"])

    # 2. 创建 news_tasks 表
    op.create_table(
        "news_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, comment="任务名称"),
        sa.Column(
            "monitor_id",
            sa.Integer(),
            sa.ForeignKey("news_monitors.id", ondelete="CASCADE"),
            nullable=False,
            comment="所属监测项目ID",
        ),
        sa.Column(
            "strategy_id",
            sa.Integer(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            nullable=True,
            comment="所属策略ID（策略流程专用）",
        ),
        sa.Column("keywords", sa.Text(), nullable=False, comment="搜索关键词"),
        sa.Column(
            "phase",
            sa.String(20),
            nullable=True,
            comment="采集阶段: probe / collect",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
            comment="任务状态: pending / running / completed / failed",
        ),
        sa.Column(
            "search_provider",
            sa.String(50),
            nullable=False,
            server_default="serpapi_baidu",
            comment="搜索提供商",
        ),
        sa.Column(
            "search_params",
            sa.JSON(),
            nullable=True,
            comment="搜索参数（时间范围、地区、最大结果数等）",
        ),
        sa.Column(
            "articles_count", sa.Integer(), server_default="0", comment="采集到的文章数量"
        ),
        sa.Column(
            "analysis_result", sa.JSON(), nullable=True, comment="分析结果（结构化洞察）"
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            comment="创建者用户ID",
        ),
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
    op.create_index("ix_news_tasks_monitor_id", "news_tasks", ["monitor_id"])
    op.create_index("ix_news_tasks_strategy_id", "news_tasks", ["strategy_id"])
    op.create_index("ix_news_tasks_status", "news_tasks", ["status"])
    op.create_index("ix_news_tasks_phase", "news_tasks", ["phase"])
    op.create_index("ix_news_tasks_created_by", "news_tasks", ["created_by"])

    # 3. strategies 表新增 news_monitor_id 字段
    op.add_column(
        "strategies",
        sa.Column(
            "news_monitor_id",
            sa.Integer(),
            sa.ForeignKey("news_monitors.id", ondelete="SET NULL"),
            nullable=True,
            comment="策略创建的新闻 Monitor ID",
        ),
    )


def downgrade() -> None:
    # 删除 strategies.news_monitor_id
    op.drop_column("strategies", "news_monitor_id")

    # 删除 news_tasks 表
    op.drop_index("ix_news_tasks_created_by", table_name="news_tasks")
    op.drop_index("ix_news_tasks_phase", table_name="news_tasks")
    op.drop_index("ix_news_tasks_status", table_name="news_tasks")
    op.drop_index("ix_news_tasks_strategy_id", table_name="news_tasks")
    op.drop_index("ix_news_tasks_monitor_id", table_name="news_tasks")
    op.drop_table("news_tasks")

    # 删除 news_monitors 表
    op.drop_index("ix_news_monitors_owner_id", table_name="news_monitors")
    op.drop_table("news_monitors")
