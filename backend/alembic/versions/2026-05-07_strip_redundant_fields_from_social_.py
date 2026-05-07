"""strip redundant fields from social slice meta

Revision ID: 8f9417832101
Revises: 07d60b879d46
Create Date: 2026-05-07 06:46:06.093604

清理 SocialSlice.result_data.meta 中四个冗余字段，源都已存在于其他权威位置：

- `meta.monitor_id` → `social_slices.monitor_id` 列
- `meta.generated_at` → `analysis_jobs.completed_at`（精确语义）
- `meta.scope.mode` → 始终硬编码 "selected_tasks"，无分支
- `meta.scope.included_task_ids` → `social_slices.included_task_ids` 列

保留 `meta.scope.platforms` / `meta.scope.keywords`（运行期从 posts 聚合）、
`meta.weights_used` / `meta.spam_config` / `meta.task_diagnostics`（LLM context
+ 前端诊断展示）。

NewsSlice.result_data 没有 meta 节点，无需处理。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8f9417832101'
down_revision: Union[str, Sequence[str], None] = '07d60b879d46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 删 meta.monitor_id 和 meta.generated_at
    op.execute(
        """
        UPDATE social_slices
        SET result_data = jsonb_set(
            result_data::jsonb,
            '{meta}',
            (result_data::jsonb -> 'meta') - 'monitor_id' - 'generated_at'
        )::json
        WHERE result_data IS NOT NULL
          AND result_data::jsonb ? 'meta';
        """
    )

    # 2. 删 meta.scope.mode 和 meta.scope.included_task_ids（保留 platforms / keywords）
    op.execute(
        """
        UPDATE social_slices
        SET result_data = jsonb_set(
            result_data::jsonb,
            '{meta,scope}',
            (result_data::jsonb -> 'meta' -> 'scope') - 'mode' - 'included_task_ids'
        )::json
        WHERE result_data IS NOT NULL
          AND result_data::jsonb -> 'meta' ? 'scope';
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 反向：把列值塞回 meta（generated_at 用 updated_at 近似，无完美还原）
    op.execute(
        """
        UPDATE social_slices
        SET result_data = jsonb_set(
            result_data::jsonb,
            '{meta}',
            COALESCE(result_data::jsonb -> 'meta', '{}'::jsonb) || jsonb_build_object(
                'monitor_id', monitor_id,
                'generated_at', to_char(updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"')
            ),
            true
        )::json
        WHERE result_data IS NOT NULL;
        """
    )

    op.execute(
        """
        UPDATE social_slices
        SET result_data = jsonb_set(
            result_data::jsonb,
            '{meta,scope}',
            COALESCE(result_data::jsonb -> 'meta' -> 'scope', '{}'::jsonb) || jsonb_build_object(
                'mode', 'selected_tasks',
                'included_task_ids', COALESCE(included_task_ids::jsonb, '[]'::jsonb)
            ),
            true
        )::json
        WHERE result_data IS NOT NULL
          AND result_data::jsonb -> 'meta' ? 'scope';
        """
    )
