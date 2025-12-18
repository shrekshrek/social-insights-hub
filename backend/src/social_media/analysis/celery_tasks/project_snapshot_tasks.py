"""项目级快照流水线 Celery 入口（Stage2 + Stage3）

实现迁移到 `project_snapshot_pipeline/orchestrator.py`，本文件只保留 Celery task 壳。
"""

from __future__ import annotations

from typing import Any

from src.celery_app import celery_app
from src.social_media.analysis.celery_tasks.project_snapshot import run_project_snapshot_pipeline_sync


def _format_terms_for_llm(term_counts: dict[str, int], top_k: int = 160) -> str:
    items = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return "\n".join([f"- {t} ({c})" for t, c in items if t and c > 0])


def _fallback_cluster_terms(term_counts: dict[str, int], threshold: float = 0.85) -> list[dict[str, Any]]:
    """规则降级：按相似度聚类，输出与 LLM parse_normalization_response 类似的结构"""
    # 按频次排序，让高频词优先成为 canonical
    terms = [t for t, c in sorted(term_counts.items(), key=lambda x: x[1], reverse=True) if t and c > 0]
    clusters: list[dict[str, Any]] = []
    used: set[str] = set()

    for t in terms:
        if t in used:
            continue
        canon = t
        originals = [t]
        used.add(t)
        for other in terms:
            if other in used:
                continue
            # normalize_name + are_similar 已包含包含关系与 SequenceMatcher
            if are_similar(canon, other, threshold=threshold):
                originals.append(other)
                used.add(other)
        clusters.append({"name": canon, "original_terms": originals})
    return clusters


def _build_term_to_cluster(clusters: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for c in clusters:
        name = (c or {}).get("name") or ""
        if not name:
            continue
        for ot in (c or {}).get("original_terms") or []:
            if isinstance(ot, str) and ot:
                mapping[ot] = name
    return mapping


def _fallback_alias_map(items: list[str], threshold: float = 0.9) -> dict[str, str]:
    """规则降级：把相似字符串映射到高频/先出现的 canonical"""
    mapping: dict[str, str] = {}
    canonicals: list[str] = []
    for it in items:
        if not it:
            continue
        assigned = None
        for c in canonicals:
            if are_similar(c, it, threshold=threshold):
                assigned = c
                break
        if assigned is None:
            canonicals.append(it)
            assigned = it
        mapping[it] = assigned
    return mapping


def _merge_attr_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """合并 entity.top_features/top_issues（按 text 累加 mentions 与分布）"""
    if not items:
        return []
    bucket: dict[str, dict[str, Any]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or "").strip()
        if not text:
            continue
        try:
            m = int(it.get("mentions") or 0)
        except Exception:
            m = 0
        if m <= 0:
            continue
        b = bucket.setdefault(text, {
            "text": text,
            "mentions": 0,
            "platform_distribution": {},
            "keyword_distribution": {},
            "original_terms": [],
        })
        b["mentions"] += m
        for k, v in (it.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = int(b["platform_distribution"].get(k, 0)) + vv
        for k, v in (it.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = int(b["keyword_distribution"].get(k, 0)) + vv
        # original_terms（若存在）简单拼接
        ots = it.get("original_terms") or []
        if isinstance(ots, list) and ots:
            b["original_terms"].extend([x for x in ots if isinstance(x, dict) and x.get("text")])
    merged = list(bucket.values())
    merged.sort(key=lambda x: x.get("mentions", 0), reverse=True)
    return merged[:10]


@celery_app.task(
    name="analysis.project_snapshot.enrich",
    bind=True,
    max_retries=0,
)
def enrich_project_snapshot_task(
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


