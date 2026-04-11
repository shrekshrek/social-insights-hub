"""cleanup_news_insight_aggregation

移除 news_monitors.aggregated_result 列（已被 NewsSlice 替代），
删除历史遗留的 news_insight 类型 AnalysisJob 记录（任务级 insight 已移除，
切片级 insight 会重新创建新的 job）。

Revision ID: a1b2c3d4e5f9
Revises: 94101c74fff0
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f9"
down_revision: Union[str, None] = "94101c74fff0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删除历史遗留的 news_insight AnalysisJob（任务级 insight 已移除）
    op.execute("DELETE FROM analysis_jobs WHERE analysis_type = 'news_insight'")

    # 移除 aggregated_result 列（监测项目级聚合已被切片替代）
    op.drop_column("news_monitors", "aggregated_result")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column(
        "news_monitors",
        sa.Column("aggregated_result", sa.JSON(), nullable=True),
    )
