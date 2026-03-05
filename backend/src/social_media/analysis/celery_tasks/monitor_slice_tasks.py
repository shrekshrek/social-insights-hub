"""项目级切片流水线 Celery 入口（Stage2 + Stage3）

实现迁移到 `monitor_slice/orchestrator.py`，本文件只保留 Celery task 壳。
"""

from __future__ import annotations

from typing import Any

from src.celery_app import celery_app
from src.social_media.analysis.celery_tasks.monitor_slice import (
    run_monitor_slice_pipeline_sync,
)
from src.social_media.analysis.constants import TOP_TERMS_FOR_LLM, MIN_CELL_MENTIONS


@celery_app.task(
    name="analysis.monitor_slice.run",
    bind=True,
    max_retries=0,
)
def run_monitor_slice_task(
    self,
    *,
    slice_id: int,
    top_terms_for_llm: int = TOP_TERMS_FOR_LLM,
    min_cell_mentions: int = MIN_CELL_MENTIONS,
) -> dict[str, Any]:
    """对项目切片执行 Stage2/Stage3 流水线（写回 result_data.stage2/stage3）。"""
    return run_monitor_slice_pipeline_sync(
        slice_id=slice_id,
        top_terms_for_llm=top_terms_for_llm,
        min_cell_mentions=min_cell_mentions,
    )
