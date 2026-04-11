"""strategy_market_report_results

为 Strategy 新增 market_report 产出路径所需字段：
- 新增三列 JSONB：market_report_a_result / market_report_b_result / market_report_c_result
- 放宽 valid_status 检查约束，补充 market_report_a_done / market_report_b_done 两个状态

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a0b1
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, None] = "c3d4e5f6a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_STATUSES = (
    "draft",
    "planned",
    "probing",
    "collecting",
    "ready",
    "phase1_done",
    "phase2_done",
    "completed",
    "market_report_a_done",
    "market_report_b_done",
)

_OLD_STATUSES = (
    "draft",
    "planned",
    "probing",
    "collecting",
    "ready",
    "phase1_done",
    "phase2_done",
    "completed",
)


def _status_in_clause(statuses: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{s}'" for s in statuses)
    return f"status IN ({joined})"


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column(
            "market_report_a_result",
            sa.JSON(),
            nullable=True,
            comment="market_report Phase A: Media Agenda Map",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "market_report_b_result",
            sa.JSON(),
            nullable=True,
            comment="market_report Phase B: Competitive Landscape + Discourse",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "market_report_c_result",
            sa.JSON(),
            nullable=True,
            comment="market_report Phase C: Strategic Brief",
        ),
    )

    op.drop_constraint("valid_status", "strategies", type_="check")
    op.create_check_constraint(
        "valid_status",
        "strategies",
        _status_in_clause(_NEW_STATUSES),
    )


def downgrade() -> None:
    op.drop_constraint("valid_status", "strategies", type_="check")
    op.create_check_constraint(
        "valid_status",
        "strategies",
        _status_in_clause(_OLD_STATUSES),
    )

    op.drop_column("strategies", "market_report_c_result")
    op.drop_column("strategies", "market_report_b_result")
    op.drop_column("strategies", "market_report_a_result")
