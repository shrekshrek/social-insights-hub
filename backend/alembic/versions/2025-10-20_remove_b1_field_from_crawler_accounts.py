"""Remove b1 field from crawler_accounts (not needed - signature service uses default value)

Revision ID: e9f3a2b7d4c5
Revises: b08a41c98cc1
Create Date: 2025-10-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9f3a2b7d4c5"
down_revision: Union[str, Sequence[str], None] = "b08a41c98cc1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - drop b1 column."""
    op.drop_column("crawler_accounts", "b1")


def downgrade() -> None:
    """Downgrade schema - restore b1 column."""
    op.add_column(
        "crawler_accounts",
        sa.Column(
            "b1",
            sa.Text(),
            nullable=True,
            comment="localStorage b1值(XHS二次签名需要)",
        ),
    )
