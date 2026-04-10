"""no-op: probe_round/parent_probe_id 已在同日迁移中添加并移除，合并为空迁移保留链路

原始两步：
  a1b2c3d4e5f7 — add probe_round + parent_probe_id
  b2c3d4e5f6a8 — drop probe_round + parent_probe_id
合并后仅保留本文件作为链路占位。

Revision ID: b2c3d4e5f6a8
Revises: f6a7b8c9d0e1
Create Date: 2026-04-09

"""

from typing import Sequence, Union

revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
