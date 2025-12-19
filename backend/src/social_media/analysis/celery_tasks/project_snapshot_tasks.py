"""项目级快照流水线 Celery 入口（Stage2 + Stage3）

实现迁移到 `project_snapshot/orchestrator.py`，本文件只保留 Celery task 壳。
"""

from __future__ import annotations

from typing import Any

from src.celery_app import celery_app
from src.social_media.analysis.celery_tasks.project_snapshot import run_project_snapshot_pipeline_sync


@celery_app.task(
    name="analysis.project_snapshot.run",
    bind=True,
    max_retries=0,
)
def run_project_snapshot_task(
    self,
    *,
    snapshot_id: int,
    top_terms_for_llm: int = 160,
    min_cell_mentions: int = 5,
) -> dict[str, Any]:
    """对项目快照执行 Stage2/Stage3 流水线（写回 result_data.stage2/stage3）。"""
    return run_project_snapshot_pipeline_sync(
        snapshot_id=snapshot_id,
        top_terms_for_llm=top_terms_for_llm,
        min_cell_mentions=min_cell_mentions,
    )


