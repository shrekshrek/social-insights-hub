"""move news slice subject/competitors into result_data.meta

Revision ID: 38072c7b2958
Revises: 78fee824d232
Create Date: 2026-05-07 03:26:56.199119

Stage1 同步重构后，subject / competitors 与社媒 SocialSlice 一致放入
`result_data.meta`，不再作为独立列。本迁移：

1. 把列值写回 `result_data.meta.subject` / `result_data.meta.competitors`，
   保留 result_data 中已有的其他键（descriptive / entities / ...）。
2. drop subject / competitors 两列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38072c7b2958'
down_revision: Union[str, Sequence[str], None] = '78fee824d232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 把列值写进 result_data.meta，保留 result_data 已有键
    op.execute(
        """
        UPDATE news_slices
        SET result_data = jsonb_set(
            COALESCE(result_data::jsonb, '{}'::jsonb),
            '{meta}',
            COALESCE(result_data::jsonb -> 'meta', '{}'::jsonb) || jsonb_build_object(
                'subject', subject,
                'competitors', COALESCE(competitors::jsonb, '[]'::jsonb)
            ),
            true
        )::json;
        """
    )

    # 2. 删除冗余列
    op.drop_column("news_slices", "competitors")
    op.drop_column("news_slices", "subject")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "news_slices",
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=True,
            comment="聚焦切片的主体品牌名（None=大盘视角）",
        ),
    )
    op.add_column(
        "news_slices",
        sa.Column(
            "competitors",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
            comment="聚焦切片的竞品品牌名列表",
        ),
    )

    # 反向回填：从 result_data.meta 恢复列值
    op.execute(
        """
        UPDATE news_slices
        SET subject = NULLIF(result_data::jsonb -> 'meta' ->> 'subject', ''),
            competitors = COALESCE(
                (result_data::jsonb -> 'meta' -> 'competitors')::json,
                '[]'::json
            )
        WHERE result_data IS NOT NULL
          AND result_data::jsonb ? 'meta';
        """
    )
