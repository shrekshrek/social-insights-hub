"""Add b1 field to crawler_accounts for XHS secondary signature

Revision ID: 22ff8a9c3c93
Revises: c97a4379015a
Create Date: 2025-10-19 03:04:08.762264

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "22ff8a9c3c93"
down_revision: Union[str, Sequence[str], None] = "c97a4379015a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "crawler_accounts",
        sa.Column(
            "b1",
            sa.String(length=255),
            nullable=True,
            comment="localStorage b1值(XHS二次签名需要)",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("crawler_accounts", "b1")
