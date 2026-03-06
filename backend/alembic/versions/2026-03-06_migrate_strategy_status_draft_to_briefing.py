"""migrate strategy status draft to briefing

Revision ID: 20260306_strategy_status
Revises: 20260306_analysis_type_rename
Create Date: 2026-03-06

- Drop old check constraint (allowed: draft/phase1_done/phase2_done/completed)
- Add new check constraint (allowed: briefing/consulting/monitors_created/slices_ready/phase1_done/phase2_done/completed)
- Migrate data: draft -> briefing
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260306_strategy_status"
down_revision: Union[str, Sequence[str], None] = "20260306_analysis_type_rename"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_CONSTRAINT = (
    "status IN ('briefing', 'consulting', 'monitors_created', 'slices_ready', "
    "'phase1_done', 'phase2_done', 'completed')"
)
OLD_CONSTRAINT = "status IN ('draft', 'phase1_done', 'phase2_done', 'completed')"


def upgrade() -> None:
    op.execute("ALTER TABLE strategies DROP CONSTRAINT ck_strategies_valid_status")
    op.execute("UPDATE strategies SET status = 'briefing' WHERE status = 'draft'")
    op.execute("ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'briefing'")
    op.execute(f"ALTER TABLE strategies ADD CONSTRAINT ck_strategies_valid_status CHECK ({NEW_CONSTRAINT})")


def downgrade() -> None:
    op.execute("UPDATE strategies SET status = 'draft' WHERE status = 'briefing'")
    op.execute("ALTER TABLE strategies ALTER COLUMN status SET DEFAULT 'draft'")
    op.execute("ALTER TABLE strategies DROP CONSTRAINT ck_strategies_valid_status")
    op.execute(f"ALTER TABLE strategies ADD CONSTRAINT ck_strategies_valid_status CHECK ({OLD_CONSTRAINT})")
