"""rename brand_strategy to campaign_strategy

Revision ID: 05361f53c559
Revises: add_operation_to_audit_logs
Create Date: 2026-04-17 07:47:44.598399

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '05361f53c559'
down_revision: Union[str, Sequence[str], None] = 'add_operation_to_audit_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename output_type value brand_strategy → campaign_strategy."""
    op.execute(
        "UPDATE strategies SET output_type = 'campaign_strategy' "
        "WHERE output_type = 'brand_strategy'"
    )


def downgrade() -> None:
    """Revert output_type value campaign_strategy → brand_strategy."""
    op.execute(
        "UPDATE strategies SET output_type = 'brand_strategy' "
        "WHERE output_type = 'campaign_strategy'"
    )
