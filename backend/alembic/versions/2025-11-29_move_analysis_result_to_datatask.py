"""add_analysis_result_to_datatask

在 social_data_tasks 表添加聚合分析结果字段。

变更内容：
1. 在 social_data_tasks 表添加 analysis_result 和 analysis_result_at 字段

设计理念：
- 聚合分析是任务级的，结果存储在 DataTask 上
- 聚合分析通过独立 API 触发 (POST /tasks/{task_id}/aggregation)
- AnalysisJob 保留用于分析任务进度跟踪

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2025-11-29 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j5e6f7g8h9i0"
down_revision: Union[str, Sequence[str], None] = "i4d5e6f7g8h9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 analysis_result 字段到 social_data_tasks 表"""

    op.add_column(
        "social_data_tasks",
        sa.Column(
            "analysis_result",
            sa.JSON(),
            nullable=True,
            comment="任务级AI分析聚合结果（NSR、SERP、实体、KANO等）",
        ),
    )
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "analysis_result_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="聚合分析生成时间",
        ),
    )


def downgrade() -> None:
    """移除 analysis_result 字段"""

    op.drop_column("social_data_tasks", "analysis_result_at")
    op.drop_column("social_data_tasks", "analysis_result")
