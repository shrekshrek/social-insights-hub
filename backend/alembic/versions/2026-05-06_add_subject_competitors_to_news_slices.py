"""add subject competitors to news_slices

Revision ID: 78fee824d232
Revises: bee8a1f06547
Create Date: 2026-05-06 18:21:17.398969

把"焦点切片配置"（subject + competitors）从仅作 Celery 调用参数升格为
NewsSlice 表上的一等列，与 SocialSlice 在前端切片列表的 Focus/大盘 徽章对齐。

Backfill 策略：
1. 关联到 strategy 的切片：从 `strategies.research_design.slice_blueprint` 按
   `(monitor_id, name)` 反推 subject / competitors。一个 strategy 引用一个
   news_monitor，blueprint 里的 name 与切片 name 一对一对应。
2. 独立监测建的切片：blueprint 反推不到的，subject=NULL, competitors=[]。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78fee824d232'
down_revision: Union[str, Sequence[str], None] = 'bee8a1f06547'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 添加列：subject 可为 null（大盘视角），competitors 默认空数组
    op.add_column(
        "news_slices",
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=True,
            comment=(
                "聚焦切片的主体品牌名（None=大盘视角，无 target/competitor 区分）。"
                "驱动 _enforce_entity_roles 的归类模式，并在前端切片列表显示 Focus/大盘 徽章。"
            ),
        ),
    )
    op.add_column(
        "news_slices",
        sa.Column(
            "competitors",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
            comment="聚焦切片的竞品品牌名列表（subject 为 None 时应为空）",
        ),
    )

    # 2. Backfill：从 strategies.research_design.slice_blueprint 反推
    # 按 (news_monitor_id, blueprint.name) → news_slices 的同名切片回填 subject/competitors
    op.execute(
        """
        WITH bp AS (
            SELECT
                s.news_monitor_id AS monitor_id,
                bp_item->>'name' AS slice_name,
                NULLIF(bp_item->>'subject', '') AS subject,
                COALESCE(bp_item->'competitors', '[]'::json) AS competitors
            FROM strategies s
            CROSS JOIN LATERAL json_array_elements(
                COALESCE(s.research_design->'slice_blueprint', '[]'::json)
            ) AS bp_item
            WHERE s.news_monitor_id IS NOT NULL
        )
        UPDATE news_slices ns
        SET subject = bp.subject,
            competitors = bp.competitors
        FROM bp
        WHERE ns.monitor_id = bp.monitor_id
          AND ns.name = bp.slice_name;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("news_slices", "competitors")
    op.drop_column("news_slices", "subject")
