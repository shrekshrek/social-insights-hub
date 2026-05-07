"""lift slice subject/competitors to columns (NewsSlice + SocialSlice)

Revision ID: 07d60b879d46
Revises: 38072c7b2958
Create Date: 2026-05-07 04:53:44.641762

把切片配置（subject + competitors）从 `result_data.meta` 内嵌升格为 NewsSlice
和 SocialSlice 表的独立列：

- 切片**配置**与切片**分析产物**解耦：LLM 重跑覆写 result_data 不再清掉配置
- 列可被 SQL 查询/索引（"列出 monitor X 下所有 Focus 切片"）
- 类型显式（Mapped[str|None] / Mapped[list[str]]）替代 dict 属性访问

社媒 result_data.meta 还保留分析时刻元数据（task_id / analyzed_at / weights_used /
scope / spam_config 等），那些是合法的分析产物，不动；只把 subject/competitors
两键搬走。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07d60b879d46'
down_revision: Union[str, Sequence[str], None] = '38072c7b2958'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_columns(table: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=True,
            comment="聚焦切片的主体品牌名（None=大盘视角 / 无 Focus）",
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "competitors",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
            comment="聚焦切片的竞品品牌名列表",
        ),
    )


def _backfill_from_meta(table: str) -> None:
    """从 result_data.meta 反向 backfill 列值。"""
    op.execute(
        f"""
        UPDATE {table}
        SET subject = NULLIF(result_data::jsonb -> 'meta' ->> 'subject', ''),
            competitors = COALESCE(
                (result_data::jsonb -> 'meta' -> 'competitors')::json,
                '[]'::json
            )
        WHERE result_data IS NOT NULL
          AND result_data::jsonb ? 'meta';
        """
    )


def _strip_meta_subject_competitors(table: str) -> None:
    """从 result_data.meta 中移除 subject 和 competitors 两键，保留其他元数据。

    社媒 meta 还有 task_id / analyzed_at / weights_used / scope 等合法字段，
    只清这两键，避免数据丢失。
    """
    op.execute(
        f"""
        UPDATE {table}
        SET result_data = jsonb_set(
            result_data::jsonb,
            '{{meta}}',
            (result_data::jsonb -> 'meta') - 'subject' - 'competitors'
        )::json
        WHERE result_data IS NOT NULL
          AND result_data::jsonb ? 'meta';
        """
    )


def upgrade() -> None:
    """Upgrade schema."""
    for table in ("news_slices", "social_slices"):
        _add_columns(table)
        _backfill_from_meta(table)
        _strip_meta_subject_competitors(table)


def downgrade() -> None:
    """Downgrade schema."""
    # 反向：把列值塞回 result_data.meta（保留 meta 已有键）
    for table in ("news_slices", "social_slices"):
        op.execute(
            f"""
            UPDATE {table}
            SET result_data = jsonb_set(
                COALESCE(result_data::jsonb, '{{}}'::jsonb),
                '{{meta}}',
                COALESCE(result_data::jsonb -> 'meta', '{{}}'::jsonb) || jsonb_build_object(
                    'subject', subject,
                    'competitors', COALESCE(competitors::jsonb, '[]'::jsonb)
                ),
                true
            )::json;
            """
        )
        op.drop_column(table, "competitors")
        op.drop_column(table, "subject")
