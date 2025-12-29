"""simplify_analysis_models_remove_comment_analysis

Revision ID: e0668138bae4
Revises: a17b43b0bdc7
Create Date: 2025-11-20 12:18:15.382014

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0668138bae4"
down_revision: Union[str, Sequence[str], None] = "a17b43b0bdc7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 添加新字段到 post_analysis 表
    op.add_column(
        "post_analysis",
        sa.Column(
            "post_deep_result",
            sa.JSON(),
            nullable=True,
            comment="帖子深度分析结果：实体、观点、摘要",
        ),
    )
    op.add_column(
        "post_analysis",
        sa.Column(
            "comment_deep_result",
            sa.JSON(),
            nullable=True,
            comment="评论深度分析聚合结果：从评论中提取的实体和观点",
        ),
    )

    # 2. 迁移数据：将 depth_analysis_result 复制到 post_deep_result
    # 注意：由于 SQLite 不支持复制列，我们使用 Python 代码迁移数据
    # 在 PostgreSQL 中可以用: UPDATE post_analysis SET post_deep_result = depth_analysis_result;
    bind = op.get_bind()
    bind.execute(
        sa.text("""
        UPDATE post_analysis
        SET post_deep_result = depth_analysis_result
        WHERE depth_analysis_result IS NOT NULL
    """)
    )

    # 3. 删除旧字段 depth_analysis_result
    with op.batch_alter_table("post_analysis", schema=None) as batch_op:
        batch_op.drop_column("depth_analysis_result")

    # 4. 删除 comment_analysis 表
    op.drop_table("comment_analysis")

    # 5. 删除 task_analysis_results 中 analysis_type = 'screening_comments' 的记录
    bind.execute(
        sa.text(
            "DELETE FROM task_analysis_results WHERE analysis_type = 'screening_comments'"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. 重新创建 comment_analysis 表
    op.create_table(
        "comment_analysis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("spam_score", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Float(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("sentiment", sa.Integer(), nullable=True),
        sa.Column("depth_analysis_result", sa.JSON(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_model", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["social_data_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["comment_id"], ["social_comments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. 添加回 depth_analysis_result 字段到 post_analysis
    op.add_column(
        "post_analysis", sa.Column("depth_analysis_result", sa.JSON(), nullable=True)
    )

    # 3. 迁移回数据
    bind = op.get_bind()
    bind.execute(
        sa.text("""
        UPDATE post_analysis
        SET depth_analysis_result = post_deep_result
        WHERE post_deep_result IS NOT NULL
    """)
    )

    # 4. 删除新字段
    with op.batch_alter_table("post_analysis", schema=None) as batch_op:
        batch_op.drop_column("comment_deep_result")
        batch_op.drop_column("post_deep_result")
