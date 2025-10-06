"""add crawler resources tables

Revision ID: 2025_10_05_001
Revises: 2025_09_30_001
Create Date: 2025-10-05 09:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2025_10_05_001"
down_revision: Union[str, None] = "2025_09_30_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reuse the existing platform enum created for crawler tasks to keep values in sync.
    platform_enum = postgresql.ENUM(name="platformtype", create_type=False)
    op.create_table(
        "crawler_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", platform_enum, nullable=False, comment="所属平台"),
        sa.Column(
            "account_name", sa.String(length=255), nullable=False, comment="账号标识"
        ),
        sa.Column("cookies", sa.Text(), nullable=False, comment="登录Cookies"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否可用",
        ),
        sa.Column(
            "locked_by_task_id", sa.Integer(), nullable=True, comment="当前占用的任务ID"
        ),
        sa.Column("locked_at", sa.DateTime(), nullable=True, comment="锁定时间"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="最近使用时间"),
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="连续失败次数",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="爬虫账号资源表",
    )
    op.create_index(
        op.f("ix_crawler_accounts_platform"),
        "crawler_accounts",
        ["platform"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_accounts_active"),
        "crawler_accounts",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "crawler_proxies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True, comment="代理标识"),
        sa.Column(
            "protocol",
            sa.String(length=32),
            nullable=False,
            server_default="http",
            comment="协议",
        ),
        sa.Column("host", sa.String(length=255), nullable=False, comment="主机地址"),
        sa.Column("port", sa.Integer(), nullable=False, comment="端口"),
        sa.Column(
            "username", sa.String(length=255), nullable=True, comment="认证用户名"
        ),
        sa.Column("password", sa.String(length=255), nullable=True, comment="认证密码"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否可用",
        ),
        sa.Column(
            "locked_by_task_id", sa.Integer(), nullable=True, comment="当前占用的任务ID"
        ),
        sa.Column("locked_at", sa.DateTime(), nullable=True, comment="锁定时间"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="最近使用时间"),
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="连续失败次数",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="爬虫代理资源表",
    )
    op.create_index(
        op.f("ix_crawler_proxies_active"),
        "crawler_proxies",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_proxies_host"), "crawler_proxies", ["host"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_crawler_proxies_host"), table_name="crawler_proxies")
    op.drop_index(op.f("ix_crawler_proxies_active"), table_name="crawler_proxies")
    op.drop_table("crawler_proxies")

    op.drop_index(op.f("ix_crawler_accounts_active"), table_name="crawler_accounts")
    op.drop_index(op.f("ix_crawler_accounts_platform"), table_name="crawler_accounts")
    op.drop_table("crawler_accounts")
