"""add strategies tables

Revision ID: e395faad75d4
Revises: 20260220_snap_to_slice
Create Date: 2026-03-04 16:41:34.815342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e395faad75d4"
down_revision: Union[str, Sequence[str], None] = "20260220_snap_to_slice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "name", sa.String(length=255), nullable=False, comment="策略名称"
        ),
        sa.Column(
            "created_by", sa.Integer(), nullable=False, comment="创建者用户ID"
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="draft",
            nullable=False,
            comment="状态: draft / phase1_done / phase2_done / completed",
        ),
        sa.Column(
            "brand_brief", sa.JSON(), nullable=True, comment="可选 Brand Brief"
        ),
        sa.Column(
            "phase1_result",
            sa.JSON(),
            nullable=True,
            comment="Phase 1: Tension + Opportunity",
        ),
        sa.Column(
            "phase2_result",
            sa.JSON(),
            nullable=True,
            comment="Phase 2: Role + Strategy",
        ),
        sa.Column(
            "phase3_result",
            sa.JSON(),
            nullable=True,
            comment="Phase 3: Big Idea + Content Strategy",
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
        sa.CheckConstraint(
            "status IN ('draft', 'phase1_done', 'phase2_done', 'completed')",
            name=op.f("ck_strategies_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_strategies_created_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategies")),
    )
    op.create_index(
        op.f("ix_strategies_created_by"),
        "strategies",
        ["created_by"],
        unique=False,
    )

    op.create_table(
        "strategy_slices",
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("slice_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["slice_id"],
            ["project_analysis_slices.id"],
            name=op.f(
                "fk_strategy_slices_slice_id_project_analysis_slices"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_strategy_slices_strategy_id_strategies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "strategy_id", "slice_id", name=op.f("pk_strategy_slices")
        ),
    )
    op.create_index(
        "idx_strategy_slices_slice_id",
        "strategy_slices",
        ["slice_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_strategy_slices_slice_id", table_name="strategy_slices")
    op.drop_table("strategy_slices")
    op.drop_index(
        op.f("ix_strategies_created_by"), table_name="strategies"
    )
    op.drop_table("strategies")
