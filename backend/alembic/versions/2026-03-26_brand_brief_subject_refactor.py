"""brand_brief subject refactor

Revision ID: 20260326_brief_subject
Revises: 5f3ad98405e9
Create Date: 2026-03-26

将 strategies 的 brand_brief JSON 中 brand_name 字段迁移为 subject，
并删除 strategies.source_plan 列（source_plan 已移入 brand_brief JSON）。
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260326_brief_subject"
down_revision: Union[str, Sequence[str], None] = "5f3ad98405e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. brand_brief JSON 中 brand_name → subject（如果 subject 尚未存在）
    # brand_brief 列为 json 类型，jsonb 运算后需显式 ::json 转回
    op.execute("""
        UPDATE strategies
        SET brand_brief = (
            CASE
                WHEN brand_brief IS NOT NULL
                     AND brand_brief::jsonb ? 'brand_name'
                     AND NOT (brand_brief::jsonb ? 'subject')
                THEN ((brand_brief::jsonb - 'brand_name')
                     || jsonb_build_object('subject', brand_brief::jsonb ->> 'brand_name'))::json
                WHEN brand_brief IS NOT NULL
                     AND brand_brief::jsonb ? 'brand_name'
                THEN (brand_brief::jsonb - 'brand_name')::json
                ELSE brand_brief
            END
        )
        WHERE brand_brief IS NOT NULL
    """)

    # 2. 删除 source_plan 列（已移入 brand_brief JSON）
    op.drop_column("strategies", "source_plan")


def downgrade() -> None:
    import sqlalchemy as sa

    # 恢复 source_plan 列
    op.add_column(
        "strategies",
        sa.Column("source_plan", sa.JSON(), nullable=True,
                  comment="AI 建议的数据源组合"),
    )

    # brand_brief JSON 中 subject → brand_name
    op.execute("""
        UPDATE strategies
        SET brand_brief = (
            CASE
                WHEN brand_brief IS NOT NULL
                     AND brand_brief::jsonb ? 'subject'
                     AND NOT (brand_brief::jsonb ? 'brand_name')
                THEN ((brand_brief::jsonb - 'subject')
                     || jsonb_build_object('brand_name', brand_brief::jsonb ->> 'subject'))::json
                WHEN brand_brief IS NOT NULL
                     AND brand_brief::jsonb ? 'subject'
                THEN (brand_brief::jsonb - 'subject')::json
                ELSE brand_brief
            END
        )
        WHERE brand_brief IS NOT NULL
    """)
