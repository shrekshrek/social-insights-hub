"""replace crawler proxies with proxy providers

Revision ID: 2025_10_07_001
Revises: 2025_10_05_001
Create Date: 2025-10-07 10:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2025_10_07_001"
down_revision: Union[str, None] = "2025_10_05_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_crawler_proxies_host"), table_name="crawler_proxies")
    op.drop_index(op.f("ix_crawler_proxies_active"), table_name="crawler_proxies")
    op.drop_table("crawler_proxies")

    op.create_table(
        "crawler_proxy_providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, comment="配置名称"),
        sa.Column(
            "provider_type",
            sa.String(length=64),
            nullable=False,
            server_default="kuaidaili",
            comment="代理商类型",
        ),
        sa.Column(
            "secret_id",
            sa.String(length=255),
            nullable=False,
            comment="快代理 secret_id",
        ),
        sa.Column(
            "signature",
            sa.String(length=255),
            nullable=False,
            comment="快代理 signature",
        ),
        sa.Column(
            "username", sa.String(length=255), nullable=False, comment="代理用户名"
        ),
        sa.Column(
            "password", sa.String(length=255), nullable=False, comment="代理密码"
        ),
        sa.Column(
            "pool_size",
            sa.Integer(),
            nullable=False,
            server_default="10",
            comment="期望池容量",
        ),
        sa.Column(
            "validate_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="启用有效性校验",
        ),
        sa.Column(
            "sync_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="5",
            comment="同步间隔(分钟)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="是否启用",
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(), nullable=True, comment="最近同步时间"
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
        comment="代理服务商配置表",
    )
    op.create_index(
        op.f("ix_crawler_proxy_providers_active"),
        "crawler_proxy_providers",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawler_proxy_providers_name"),
        "crawler_proxy_providers",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_crawler_proxy_providers_name"),
        table_name="crawler_proxy_providers",
    )
    op.drop_index(
        op.f("ix_crawler_proxy_providers_active"),
        table_name="crawler_proxy_providers",
    )
    op.drop_table("crawler_proxy_providers")

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
        op.f("ix_crawler_proxies_host"), "crawler_proxies", ["host"], unique=False
    )
    op.create_index(
        op.f("ix_crawler_proxies_active"),
        "crawler_proxies",
        ["is_active"],
        unique=False,
    )
