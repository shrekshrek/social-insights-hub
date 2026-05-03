"""campaign_strategy 多分支重构：brand_role_result/big_idea_result -> brand_strategy_branches

把 strategies 表的单 brand_role_result + 单 big_idea_result 字段改造成
brand_strategy_branches list 字段，每个元素对应 insight 中一个 tension 的独立
brand_role + big_idea 路径。现有有数据的策略，回填为单元素 list（tension_id=0,
selected=true）保留产出。

Revision ID: bee8a1f06547
Revises: f1e96931e5e9
Create Date: 2026-05-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bee8a1f06547'
down_revision: Union[str, Sequence[str], None] = 'f1e96931e5e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 加新列
    op.add_column(
        'strategies',
        sa.Column(
            'brand_strategy_branches',
            sa.JSON(),
            nullable=True,
            comment='campaign_strategy 第 2/3 层多分支：每个 insight tension 独立 brand_role + big_idea 路径',
        ),
    )

    # 2. 回填：现有有 brand_role_result OR big_idea_result 数据的策略，
    #    转成单元素 branches list，selected=true 保持原行为
    op.execute("""
        UPDATE strategies
        SET brand_strategy_branches = jsonb_build_array(
            jsonb_build_object(
                'tension_id', 0,
                'tension_summary', '',
                'brand_role', brand_role_result::jsonb,
                'big_idea', big_idea_result::jsonb,
                'selected', true,
                'status', CASE
                    WHEN big_idea_result IS NOT NULL THEN 'big_idea_done'
                    WHEN brand_role_result IS NOT NULL THEN 'brand_role_done'
                    ELSE 'pending'
                END
            )
        )
        WHERE brand_role_result IS NOT NULL OR big_idea_result IS NOT NULL
    """)

    # 3. 删旧列
    op.drop_column('strategies', 'big_idea_result')
    op.drop_column('strategies', 'brand_role_result')


def downgrade() -> None:
    """Downgrade schema."""
    # 恢复旧列
    op.add_column(
        'strategies',
        sa.Column(
            'brand_role_result',
            sa.JSON(),
            nullable=True,
            comment='campaign_strategy 第 2 层 Brand Role: Role + Strategy',
        ),
    )
    op.add_column(
        'strategies',
        sa.Column(
            'big_idea_result',
            sa.JSON(),
            nullable=True,
            comment='campaign_strategy 第 3 层 Big Idea: Big Idea + Content Strategy',
        ),
    )

    # 从 branches 回填旧列：取 selected=true 的分支（无则取第一个）
    op.execute("""
        UPDATE strategies
        SET
            brand_role_result = COALESCE(
                (SELECT (b->>'brand_role')::jsonb
                 FROM jsonb_array_elements(brand_strategy_branches) b
                 WHERE (b->>'selected')::bool = true
                 LIMIT 1),
                (SELECT (b->>'brand_role')::jsonb
                 FROM jsonb_array_elements(brand_strategy_branches) b
                 LIMIT 1)
            ),
            big_idea_result = COALESCE(
                (SELECT (b->>'big_idea')::jsonb
                 FROM jsonb_array_elements(brand_strategy_branches) b
                 WHERE (b->>'selected')::bool = true
                 LIMIT 1),
                (SELECT (b->>'big_idea')::jsonb
                 FROM jsonb_array_elements(brand_strategy_branches) b
                 LIMIT 1)
            )
        WHERE brand_strategy_branches IS NOT NULL
            AND jsonb_array_length(brand_strategy_branches) > 0
    """)

    op.drop_column('strategies', 'brand_strategy_branches')
