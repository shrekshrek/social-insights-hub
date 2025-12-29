"""add_agent_task_fields

为 DataTask 添加爬虫任务相关字段：
- priority: 任务优先级
- crawled_count: 已爬取数量
- accepted_at: 爬虫接收时间
- accepted_by: 执行客户端标识

Revision ID: m3c4d5e6f7g8
Revises: l2b3c4d5e6f7
Create Date: 2025-12-29 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m3c4d5e6f7g8"
down_revision: Union[str, Sequence[str], None] = "l2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 priority 字段
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="任务优先级（越大越优先）",
        ),
    )

    # 添加 crawled_count 字段
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "crawled_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已爬取数量（进度）",
        ),
    )

    # 添加 accepted_at 字段
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="爬虫接收时间",
        ),
    )

    # 添加 accepted_by 字段
    op.add_column(
        "social_data_tasks",
        sa.Column(
            "accepted_by",
            sa.String(100),
            nullable=True,
            comment="执行客户端标识",
        ),
    )


def downgrade() -> None:
    op.drop_column("social_data_tasks", "accepted_by")
    op.drop_column("social_data_tasks", "accepted_at")
    op.drop_column("social_data_tasks", "crawled_count")
    op.drop_column("social_data_tasks", "priority")
