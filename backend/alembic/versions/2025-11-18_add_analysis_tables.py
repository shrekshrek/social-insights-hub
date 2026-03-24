"""add_analysis_tables

Revision ID: a17b43b0bdc7
Revises: 446c6784a0df
Create Date: 2025-11-18 19:54:48.645018

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a17b43b0bdc7"
down_revision: Union[str, Sequence[str], None] = "446c6784a0df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add analysis tables."""

    # Create post_analysis table
    op.create_table(
        "post_analysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False, comment="关联的数据任务ID"),
        sa.Column("post_id", sa.Integer(), nullable=False, comment="关联的原文ID"),
        sa.Column(
            "spam_score",
            sa.Float(),
            nullable=True,
            comment="垃圾分（0-10，分数越高越像垃圾）",
        ),
        sa.Column(
            "value_score",
            sa.Float(),
            nullable=True,
            comment="价值分（0-10，分数越高价值越大）",
        ),
        sa.Column(
            "relevance_score",
            sa.Float(),
            nullable=True,
            comment="相关度分（0-10，分数越高相关度越高）",
        ),
        sa.Column(
            "sentiment",
            sa.Integer(),
            nullable=True,
            comment="情感倾向（-1: 负面, 0: 中性, 1: 正面）",
        ),
        sa.Column(
            "depth_analysis_result",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="深度分析结果（JSON格式）",
        ),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="分析完成时间",
        ),
        sa.Column(
            "analysis_model",
            sa.String(length=100),
            nullable=True,
            comment="使用的AI模型",
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id"),  # 一对一关系
    )
    op.create_index(
        "idx_post_analysis_scores",
        "post_analysis",
        ["spam_score", "value_score", "relevance_score"],
    )
    op.create_index("idx_post_analysis_task_id", "post_analysis", ["task_id"])

    # Create comment_analysis table
    op.create_table(
        "comment_analysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False, comment="关联的数据任务ID"),
        sa.Column("comment_id", sa.Integer(), nullable=False, comment="关联的评论ID"),
        sa.Column(
            "spam_score",
            sa.Float(),
            nullable=True,
            comment="垃圾分（0-10，分数越高越像垃圾）",
        ),
        sa.Column(
            "value_score",
            sa.Float(),
            nullable=True,
            comment="价值分（0-10，分数越高价值越大）",
        ),
        sa.Column(
            "relevance_score",
            sa.Float(),
            nullable=True,
            comment="相关度分（0-10，分数越高相关度越高）",
        ),
        sa.Column(
            "sentiment",
            sa.Integer(),
            nullable=True,
            comment="情感倾向（-1: 负面, 0: 中性, 1: 正面）",
        ),
        sa.Column(
            "depth_analysis_result",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="深度分析结果（JSON格式）",
        ),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="分析完成时间",
        ),
        sa.Column(
            "analysis_model",
            sa.String(length=100),
            nullable=True,
            comment="使用的AI模型",
        ),
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
        sa.ForeignKeyConstraint(
            ["comment_id"], ["social_comments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_id"),  # 一对一关系
    )
    op.create_index(
        "idx_comment_analysis_scores",
        "comment_analysis",
        ["spam_score", "value_score", "relevance_score"],
    )
    op.create_index("idx_comment_analysis_task_id", "comment_analysis", ["task_id"])

    # Create task_analysis_results table
    op.create_table(
        "task_analysis_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False, comment="关联的数据任务ID"),
        sa.Column(
            "analysis_type",
            sa.String(length=50),
            nullable=False,
            comment="分析类型: screening_posts/screening_comments/deep_posts/deep_comments",
        ),
        sa.Column(
            "result_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="分析结果数据（JSON格式）",
        ),
        sa.Column("analysis_summary", sa.Text(), nullable=True, comment="分析摘要"),
        sa.Column(
            "source_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="源数据数量",
        ),
        sa.Column(
            "analyzed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="成功分析数量",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="失败数量",
        ),
        sa.Column(
            "celery_task_id",
            sa.String(length=255),
            nullable=False,
            comment="Celery任务ID",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
            comment="状态: pending/processing/completed/failed",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="任务开始时间",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="任务完成时间",
        ),
        sa.Column(
            "processing_time", sa.Integer(), nullable=True, comment="处理耗时（秒）"
        ),
        sa.Column(
            "token_usage",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="Token使用统计（包含成本信息）",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
    )
    op.create_index(
        "idx_task_analysis_type_status",
        "task_analysis_results",
        ["analysis_type", "status"],
    )
    op.create_index(
        "idx_task_analysis_created_at", "task_analysis_results", ["created_at"]
    )

    # Create project_analysis_results table
    op.create_table(
        "project_analysis_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False, comment="关联的项目ID"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="执行分析的用户ID"),
        sa.Column(
            "analysis_type",
            sa.String(length=50),
            nullable=False,
            comment="分析类型: topic_clustering/competitive_analysis",
        ),
        sa.Column(
            "analysis_config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="分析配置参数",
        ),
        sa.Column(
            "source_task_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="源任务ID列表",
        ),
        sa.Column(
            "source_data_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="源数据总数",
        ),
        sa.Column(
            "result_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="分析结果数据（JSON格式）",
        ),
        sa.Column("analysis_summary", sa.Text(), nullable=True, comment="分析结果摘要"),
        sa.Column(
            "celery_task_id",
            sa.String(length=255),
            nullable=False,
            comment="Celery任务ID",
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
            comment="状态: pending/processing/completed/failed",
        ),
        sa.Column(
            "processing_time", sa.Integer(), nullable=True, comment="处理耗时（秒）"
        ),
        sa.Column(
            "token_usage",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="Token使用统计（包含成本信息）",
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="完成时间",
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
    )
    op.create_index(
        "idx_project_analysis_type_status",
        "project_analysis_results",
        ["analysis_type", "status"],
    )
    op.create_index(
        "idx_project_analysis_created_at", "project_analysis_results", ["created_at"]
    )
    op.create_index(
        "idx_project_analysis_project_user",
        "project_analysis_results",
        ["project_id", "user_id"],
    )


def downgrade() -> None:
    """Downgrade schema to remove analysis tables."""
    op.drop_table("project_analysis_results")
    op.drop_table("task_analysis_results")
    op.drop_table("comment_analysis")
    op.drop_table("post_analysis")
