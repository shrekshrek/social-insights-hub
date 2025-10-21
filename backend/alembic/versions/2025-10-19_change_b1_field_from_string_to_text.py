"""Change b1 field from String to Text

Revision ID: b08a41c98cc1
Revises: 22ff8a9c3c93
Create Date: 2025-10-19 03:36:38.062870

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b08a41c98cc1"
down_revision: Union[str, Sequence[str], None] = "22ff8a9c3c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Change b1 column from VARCHAR(255) to TEXT
    op.alter_column(
        "crawler_accounts",
        "b1",
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Change b1 column back to VARCHAR(255)
    op.alter_column(
        "crawler_accounts",
        "b1",
        type_=sa.String(length=255),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
