"""remove_project_platforms_table_and_keywords

Revision ID: 446c6784a0df
Revises: c5d4e8f9a2b3
Create Date: 2025-11-15 23:56:09.890334

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "446c6784a0df"
down_revision: Union[str, Sequence[str], None] = "c5d4e8f9a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove project-platform relationship table and keywords column."""
    # 删除项目-平台关联表
    op.drop_table("social_project_platform_assignments")

    # 删除项目的keywords列
    op.drop_column("social_projects", "keywords")


def downgrade() -> None:
    """Restore project-platform relationship table and keywords column."""
    # 重建keywords列
    op.add_column("social_projects", sa.Column("keywords", sa.Text(), nullable=True))

    # 重建项目-平台关联表
    op.create_table(
        "social_project_platform_assignments",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["platform_id"], ["platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["social_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "platform_id"),
    )
