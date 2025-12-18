from __future__ import annotations

import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.langchain.chains.project_snapshot_summary_chain import (
    create_project_snapshot_summary_chain,
    parse_project_snapshot_summary_response,
)

logger = logging.getLogger(__name__)


def generate_project_summary(
    *,
    meta: dict[str, Any],
    overview: dict[str, Any],
    charts: dict[str, Any],
    topic_aspects_aligned_v2: list[dict[str, Any]],
    entities_aligned: list[dict[str, Any]],
    topics_aligned: list[dict[str, Any]],
    drivers_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    """Stage3：整体总结（LLM Analyst）。"""
    diffs = {
        "quadrant_summary": (charts or {}).get("quadrant_summary"),
        "quadrant_summary_by_platform": (charts or {}).get("quadrant_summary_by_platform"),
        "quadrant_summary_by_keyword": (charts or {}).get("quadrant_summary_by_keyword"),
    }

    try:
        chain = create_project_snapshot_summary_chain()
        resp, stats = invoke_chain_with_stats_sync(chain, {
            "meta": str(meta)[:4000],
            "overview": str(overview)[:4000],
            "differences": str(diffs)[:6000],
            "topic_aspects": str((topic_aspects_aligned_v2 or [])[:20])[:6000],
            "top_entities": str((entities_aligned or [])[:40])[:9000],
            "top_topics": str((topics_aligned or [])[:40])[:9000],
            "drivers_matrix": str((drivers_matrix or [])[:16])[:9000],
        }, "chat")
        text = resp.content if hasattr(resp, "content") else str(resp)
        summary = parse_project_snapshot_summary_response(text)
        return {
            "status": "completed" if summary else "failed",
            "llm": {"used": True, "token_stats": stats},
            "summary": summary,
            "error": None if summary else "empty_summary",
        }
    except Exception as e:
        logger.error(f"[Snapshot Stage3] Summary generation failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "llm": {"used": False},
            "summary": None,
            "error": str(e)[:300],
        }


