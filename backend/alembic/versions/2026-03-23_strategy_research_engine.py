"""strategy research engine

Revision ID: 20260323_strat_research_eng
Revises: 20260306_strategy_status
Create Date: 2026-03-23

Strategy 模块从"末端消费者"重构为"智能研究编排者"：
- 替换字段: consultation_rounds → research_design
- 替换字段: suggested_monitor_ids → monitor_id (FK → monitors.id)
- 替换字段: evaluation_result → coverage_check_result
- 移除字段: slice_plan (包含在 research_design.slice_blueprint 中)
- 新增字段: probe_review_result, probe_round, output_type, task_ids
- 状态枚举: briefing/consulting/monitors_created/slices_ready →
            draft/planned/probing/collecting/ready
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260323_strat_research_eng"
down_revision: Union[str, Sequence[str], None] = "20260306_strategy_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. 新增列 ─────────────────────────────────────────────────
    op.add_column(
        "strategies",
        sa.Column(
            "research_design", sa.JSON(), nullable=True,
            comment="研究设计（research_design_chain 输出）",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "probe_review_result", sa.JSON(), nullable=True,
            comment="探测审查结果（probe_review_chain 输出）",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "probe_round", sa.Integer(), server_default="0", nullable=False,
            comment="当前探测轮次（最多 3）",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "coverage_check_result", sa.JSON(), nullable=True,
            comment="覆盖度验证结果（coverage_check_chain 输出）",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "output_type", sa.String(length=30), nullable=True,
            comment="产出类型: brand_strategy / insight_report",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "task_ids", sa.JSON(), server_default="[]", nullable=False,
            comment="策略创建的所有 DataTask ID",
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "monitor_id", sa.Integer(), nullable=True,
            comment="策略创建的 Monitor ID",
        ),
    )
    op.create_foreign_key(
        op.f("fk_strategies_monitor_id_monitors"),
        "strategies", "monitors",
        ["monitor_id"], ["id"],
    )

    # ── 2. 数据迁移：旧字段 → 新字段 ──────────────────────────────
    # consultation_rounds → research_design（取最新一轮的 ai_response）
    # 注意：旧列是 json 类型，需要 ::jsonb 显式转换后才能用 jsonb 运算符
    op.execute("""
        UPDATE strategies SET research_design = (
            CASE
                WHEN consultation_rounds IS NOT NULL
                     AND consultation_rounds::jsonb != '[]'::jsonb
                THEN consultation_rounds::jsonb -> -1 -> 'ai_response'
                ELSE NULL
            END
        )
    """)

    # suggested_monitor_ids → monitor_id（取第一个元素）
    op.execute("""
        UPDATE strategies SET monitor_id = (
            CASE
                WHEN suggested_monitor_ids IS NOT NULL
                     AND suggested_monitor_ids::jsonb != '[]'::jsonb
                     AND jsonb_array_length(suggested_monitor_ids::jsonb) > 0
                THEN (suggested_monitor_ids::jsonb -> 0)::int
                ELSE NULL
            END
        )
    """)

    # evaluation_result → coverage_check_result
    op.execute("""
        UPDATE strategies SET coverage_check_result = evaluation_result
    """)

    # ── 3. 状态映射 ────────────────────────────────────────────────
    # 先解除旧约束，否则新状态值写入会被拒绝
    op.execute("ALTER TABLE strategies DROP CONSTRAINT ck_strategies_valid_status")

    op.execute("UPDATE strategies SET status = 'draft' WHERE status = 'briefing'")
    op.execute("UPDATE strategies SET status = 'planned' WHERE status = 'consulting'")
    op.execute("UPDATE strategies SET status = 'collecting' WHERE status = 'monitors_created'")
    op.execute("UPDATE strategies SET status = 'ready' WHERE status = 'slices_ready'")

    op.execute("ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'draft'")

    # ── 4. 删除旧列 ────────────────────────────────────────────────
    op.drop_column("strategies", "consultation_rounds")
    op.drop_column("strategies", "suggested_monitor_ids")
    op.drop_column("strategies", "slice_plan")
    op.drop_column("strategies", "evaluation_result")

    # ── 5. 添加新约束 ──────────────────────────────────────────────
    op.execute(
        "ALTER TABLE strategies ADD CONSTRAINT ck_strategies_valid_status "
        "CHECK (status IN ("
        "'draft', 'planned', 'probing', 'collecting', 'ready', "
        "'phase1_done', 'phase2_done', 'completed'"
        "))"
    )


def downgrade() -> None:
    # ── 恢复旧约束 ─────────────────────────────────────────────────
    op.execute("ALTER TABLE strategies DROP CONSTRAINT ck_strategies_valid_status")

    # ── 恢复旧列 ───────────────────────────────────────────────────
    op.add_column(
        "strategies",
        sa.Column(
            "consultation_rounds", sa.JSON(),
            server_default="[]", nullable=False,
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "suggested_monitor_ids", sa.JSON(),
            server_default="[]", nullable=False,
        ),
    )
    op.add_column(
        "strategies",
        sa.Column(
            "slice_plan", sa.JSON(),
            server_default="[]", nullable=False,
        ),
    )
    op.add_column(
        "strategies",
        sa.Column("evaluation_result", sa.JSON(), nullable=True),
    )

    # ── 数据回迁 ───────────────────────────────────────────────────
    op.execute("""
        UPDATE strategies SET evaluation_result = coverage_check_result
    """)
    op.execute("""
        UPDATE strategies SET suggested_monitor_ids = (
            CASE
                WHEN monitor_id IS NOT NULL
                THEN jsonb_build_array(monitor_id)
                ELSE '[]'::jsonb
            END
        )
    """)

    # ── 状态回迁 ───────────────────────────────────────────────────
    op.execute("UPDATE strategies SET status = 'briefing' WHERE status = 'draft'")
    op.execute("UPDATE strategies SET status = 'consulting' WHERE status = 'planned'")
    op.execute("UPDATE strategies SET status = 'monitors_created' WHERE status = 'collecting'")
    op.execute("UPDATE strategies SET status = 'slices_ready' WHERE status = 'ready'")
    # probing 无旧状态对应，回退到 consulting
    op.execute("UPDATE strategies SET status = 'consulting' WHERE status = 'probing'")

    op.execute("ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'briefing'")

    # ── 删除新列 ───────────────────────────────────────────────────
    op.drop_constraint(
        op.f("fk_strategies_monitor_id_monitors"),
        "strategies", type_="foreignkey",
    )
    op.drop_column("strategies", "monitor_id")
    op.drop_column("strategies", "task_ids")
    op.drop_column("strategies", "output_type")
    op.drop_column("strategies", "coverage_check_result")
    op.drop_column("strategies", "probe_round")
    op.drop_column("strategies", "probe_review_result")
    op.drop_column("strategies", "research_design")

    # ── 恢复旧约束 ─────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE strategies ADD CONSTRAINT ck_strategies_valid_status "
        "CHECK (status IN ("
        "'briefing', 'consulting', 'monitors_created', 'slices_ready', "
        "'phase1_done', 'phase2_done', 'completed'"
        "))"
    )
