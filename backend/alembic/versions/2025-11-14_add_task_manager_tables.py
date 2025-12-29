"""add task manager tables

Revision ID: c5d4e8f9a2b3
Revises: b4c8d3e9f5a1
Create Date: 2025-11-14 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5d4e8f9a2b3"
down_revision: Union[str, Sequence[str], None] = "b4c8d3e9f5a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add task manager tables."""

    # Create social_data_tasks table
    op.create_table(
        "social_data_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            sa.String(length=50),
            nullable=False,
            comment="任务类型: search/detail/creator/homefeed",
        ),
        sa.Column(
            "keywords", sa.Text(), nullable=True, comment="搜索关键词（仅search类型）"
        ),
        sa.Column(
            "task_params",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="任务参数（JSON格式）",
        ),
        sa.Column(
            "data_source",
            sa.String(length=50),
            nullable=False,
            comment="数据源: remote_crawler/local_upload",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
            comment="任务状态: pending/running/completed/failed",
        ),
        sa.Column(
            "posts_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="原文数量",
        ),
        sa.Column(
            "comments_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="评论数量",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["social_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_data_tasks_name", "social_data_tasks", ["name"])
    op.create_index(
        "ix_social_data_tasks_project_id", "social_data_tasks", ["project_id"]
    )
    op.create_index(
        "ix_social_data_tasks_platform_id", "social_data_tasks", ["platform_id"]
    )
    op.create_index(
        "ix_social_data_tasks_creator_id", "social_data_tasks", ["creator_id"]
    )
    op.create_index(
        "ix_social_data_tasks_task_type", "social_data_tasks", ["task_type"]
    )
    op.create_index(
        "ix_social_data_tasks_data_source", "social_data_tasks", ["data_source"]
    )
    op.create_index("ix_social_data_tasks_status", "social_data_tasks", ["status"])
    op.create_index(
        "ix_social_data_tasks_is_deleted", "social_data_tasks", ["is_deleted"]
    )

    # Create social_posts table
    op.create_table(
        "social_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column(
            "post_id_on_platform",
            sa.String(length=255),
            nullable=False,
            comment="平台上的帖子ID",
        ),
        sa.Column("post_type", sa.String(length=50), nullable=True, comment="帖子类型"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("author_id", sa.String(length=255), nullable=True, comment="作者ID"),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "images",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="图片URL列表",
        ),
        sa.Column(
            "videos",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="视频URL列表",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=True, comment="帖子URL"),
        sa.Column(
            "raw_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="平台返回的原始JSON",
        ),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="数据采集时间",
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["social_data_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_posts_task_id", "social_posts", ["task_id"])
    op.create_index("ix_social_posts_platform_id", "social_posts", ["platform_id"])
    op.create_index(
        "ix_social_posts_post_id_on_platform", "social_posts", ["post_id_on_platform"]
    )
    op.create_index("ix_social_posts_is_deleted", "social_posts", ["is_deleted"])
    # 复合索引：支持跨任务查询同一帖子
    op.create_index(
        "ix_post_platform_postid",
        "social_posts",
        ["platform_id", "post_id_on_platform"],
    )

    # Create social_comments table
    op.create_table(
        "social_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column(
            "comment_id_on_platform",
            sa.String(length=255),
            nullable=False,
            comment="平台上的评论ID",
        ),
        sa.Column(
            "parent_comment_id",
            sa.String(length=255),
            nullable=True,
            comment="父评论ID（用于楼中楼）",
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("author_id", sa.String(length=255), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "sub_comments_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="子评论数",
        ),
        sa.Column("images", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="数据采集时间",
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["social_data_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["post_id"], ["social_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_comments_task_id", "social_comments", ["task_id"])
    op.create_index("ix_social_comments_post_id", "social_comments", ["post_id"])
    op.create_index(
        "ix_social_comments_platform_id", "social_comments", ["platform_id"]
    )
    op.create_index(
        "ix_social_comments_comment_id_on_platform",
        "social_comments",
        ["comment_id_on_platform"],
    )
    op.create_index("ix_social_comments_is_deleted", "social_comments", ["is_deleted"])
    # 复合索引：支持评论去重和查询优化
    op.create_index(
        "ix_comment_platform_commentid",
        "social_comments",
        ["platform_id", "comment_id_on_platform"],
    )
    op.create_index("ix_comment_post", "social_comments", ["post_id", "collected_at"])


def downgrade() -> None:
    """Downgrade schema by removing task manager tables."""
    op.drop_index("ix_comment_post", table_name="social_comments")
    op.drop_index("ix_comment_platform_commentid", table_name="social_comments")
    op.drop_index("ix_social_comments_is_deleted", table_name="social_comments")
    op.drop_index(
        "ix_social_comments_comment_id_on_platform", table_name="social_comments"
    )
    op.drop_index("ix_social_comments_platform_id", table_name="social_comments")
    op.drop_index("ix_social_comments_post_id", table_name="social_comments")
    op.drop_index("ix_social_comments_task_id", table_name="social_comments")
    op.drop_table("social_comments")

    op.drop_index("ix_post_platform_postid", table_name="social_posts")
    op.drop_index("ix_social_posts_is_deleted", table_name="social_posts")
    op.drop_index("ix_social_posts_post_id_on_platform", table_name="social_posts")
    op.drop_index("ix_social_posts_platform_id", table_name="social_posts")
    op.drop_index("ix_social_posts_task_id", table_name="social_posts")
    op.drop_table("social_posts")

    op.drop_index("ix_social_data_tasks_is_deleted", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_status", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_data_source", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_task_type", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_creator_id", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_platform_id", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_project_id", table_name="social_data_tasks")
    op.drop_index("ix_social_data_tasks_name", table_name="social_data_tasks")
    op.drop_table("social_data_tasks")
