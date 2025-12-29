"""add social media tables

Revision ID: b4c8d3e9f5a1
Revises: aa99cf3f13cf
Create Date: 2025-11-14 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4c8d3e9f5a1"
down_revision: Union[str, Sequence[str], None] = "aa99cf3f13cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add social media tables."""

    # Create platforms table
    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("icon_url", sa.String(length=512), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platforms")),
        sa.UniqueConstraint("name", name=op.f("uq_platforms_name")),
        sa.UniqueConstraint("code", name=op.f("uq_platforms_code")),
    )
    op.create_index(op.f("ix_platforms_name"), "platforms", ["name"], unique=False)
    op.create_index(op.f("ix_platforms_code"), "platforms", ["code"], unique=False)

    # Create social_projects table
    op.create_table(
        "social_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("project_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("project_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deep_analysis_settings",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
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
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_social_projects_owner_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_projects")),
        sa.UniqueConstraint("name", name=op.f("uq_social_projects_name")),
    )
    op.create_index(
        op.f("ix_social_projects_name"), "social_projects", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_social_projects_owner_id"),
        "social_projects",
        ["owner_id"],
        unique=False,
    )

    # Create social_project_platform_assignments (many-to-many)
    op.create_table(
        "social_project_platform_assignments",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["platform_id"],
            ["platforms.id"],
            name=op.f("fk_social_project_platform_assignments_platform_id_platforms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["social_projects.id"],
            name=op.f(
                "fk_social_project_platform_assignments_project_id_social_projects"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "platform_id",
            name=op.f("pk_social_project_platform_assignments"),
        ),
    )

    # Create social_project_participants (many-to-many)
    op.create_table(
        "social_project_participants",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["social_projects.id"],
            name=op.f("fk_social_project_participants_project_id_social_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_social_project_participants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "user_id", name=op.f("pk_social_project_participants")
        ),
    )


def downgrade() -> None:
    """Downgrade schema to remove social media tables."""
    op.drop_table("social_project_participants")
    op.drop_table("social_project_platform_assignments")
    op.drop_index(op.f("ix_social_projects_owner_id"), table_name="social_projects")
    op.drop_index(op.f("ix_social_projects_name"), table_name="social_projects")
    op.drop_table("social_projects")
    op.drop_index(op.f("ix_platforms_code"), table_name="platforms")
    op.drop_index(op.f("ix_platforms_name"), table_name="platforms")
    op.drop_table("platforms")
