"""strategy_semantic_rename

策略模块语义重命名（Option 2 full rename）：
- Strategy 结果列：
    phase1_result          → insight_result
    phase2_result          → brand_role_result
    phase3_result          → big_idea_result
    market_report_a_result → agenda_map_result
    market_report_b_result → landscape_result
    market_report_c_result → strategic_brief_result
- Strategy.status 取值：
    phase1_done            → insight_done
    phase2_done            → brand_role_done
    market_report_a_done   → agenda_map_done
    market_report_b_done   → landscape_done
    （phase3_done / market_report_c_done 本来就直接进 completed）
- valid_status 检查约束替换为新取值
- analysis_jobs.analysis_type：
    strategy_phase1          → strategy_insight
    strategy_phase2          → strategy_brand_role
    strategy_phase3          → strategy_big_idea
    strategy_market_report_a → strategy_agenda_map
    strategy_market_report_b → strategy_landscape
    strategy_market_report_c → strategy_strategic_brief

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: Union[str, None] = "e5f6a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMN_RENAMES: tuple[tuple[str, str], ...] = (
    ("phase1_result", "insight_result"),
    ("phase2_result", "brand_role_result"),
    ("phase3_result", "big_idea_result"),
    ("market_report_a_result", "agenda_map_result"),
    ("market_report_b_result", "landscape_result"),
    ("market_report_c_result", "strategic_brief_result"),
)

_STATUS_RENAMES: tuple[tuple[str, str], ...] = (
    ("phase1_done", "insight_done"),
    ("phase2_done", "brand_role_done"),
    ("market_report_a_done", "agenda_map_done"),
    ("market_report_b_done", "landscape_done"),
)

_ANALYSIS_TYPE_RENAMES: tuple[tuple[str, str], ...] = (
    ("strategy_phase1", "strategy_insight"),
    ("strategy_phase2", "strategy_brand_role"),
    ("strategy_phase3", "strategy_big_idea"),
    ("strategy_market_report_a", "strategy_agenda_map"),
    ("strategy_market_report_b", "strategy_landscape"),
    ("strategy_market_report_c", "strategy_strategic_brief"),
)

_NEW_STATUSES = (
    "draft",
    "planned",
    "probing",
    "collecting",
    "ready",
    "insight_done",
    "brand_role_done",
    "agenda_map_done",
    "landscape_done",
    "completed",
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
    "market_report_a_done",
    "market_report_b_done",
)


def _status_in_clause(statuses: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{s}'" for s in statuses)
    return f"status IN ({joined})"


def upgrade() -> None:
    # 1. 重命名 strategies 表的 6 个 JSONB 列
    for old, new in _COLUMN_RENAMES:
        op.alter_column("strategies", old, new_column_name=new)

    # 2. 先放宽约束（兼容新老值），再迁移数据，最后收紧到新值
    op.drop_constraint("valid_status", "strategies", type_="check")

    # 2a. 迁移 Strategy.status 取值
    for old, new in _STATUS_RENAMES:
        op.execute(
            f"UPDATE strategies SET status = '{new}' WHERE status = '{old}'"
        )

    # 2b. 重新建立检查约束（仅允许新取值）
    op.create_check_constraint(
        "valid_status",
        "strategies",
        _status_in_clause(_NEW_STATUSES),
    )

    # 3. 迁移 analysis_jobs.analysis_type 的策略类型
    for old, new in _ANALYSIS_TYPE_RENAMES:
        op.execute(
            f"UPDATE analysis_jobs SET analysis_type = '{new}' "
            f"WHERE analysis_type = '{old}'"
        )


def downgrade() -> None:
    # 反向迁移 analysis_jobs.analysis_type
    for old, new in _ANALYSIS_TYPE_RENAMES:
        op.execute(
            f"UPDATE analysis_jobs SET analysis_type = '{old}' "
            f"WHERE analysis_type = '{new}'"
        )

    # 反向迁移 Strategy.status 取值 + 约束
    op.drop_constraint("valid_status", "strategies", type_="check")
    for old, new in _STATUS_RENAMES:
        op.execute(
            f"UPDATE strategies SET status = '{old}' WHERE status = '{new}'"
        )
    op.create_check_constraint(
        "valid_status",
        "strategies",
        _status_in_clause(_OLD_STATUSES),
    )

    # 反向重命名列
    for old, new in _COLUMN_RENAMES:
        op.alter_column("strategies", new, new_column_name=old)
