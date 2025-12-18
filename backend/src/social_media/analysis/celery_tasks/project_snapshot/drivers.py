from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.langchain.chains.attribute_normalization_chain import (
    create_attribute_normalization_chain,
    parse_normalization_response,
)

from .utils import format_terms_for_llm, fallback_cluster_terms, build_term_to_cluster

logger = logging.getLogger(__name__)


def build_drivers_from_entities(
    *,
    top_entities: list[dict[str, Any]],
    top_terms_for_llm: int = 160,
    min_cell_mentions: int = 5,
) -> dict[str, Any]:
    """Stage2-A1：实体属性归纳/聚类 + 实体×维度矩阵（基于 Stage1 top_features/top_issues）。"""
    term_counts: dict[str, int] = {}
    entity_terms: dict[str, dict[str, dict[str, Any]]] = {}

    for e in top_entities or []:
        if not isinstance(e, dict):
            continue
        entity_name = (e.get("name") or "").strip()
        if not entity_name:
            continue
        per = entity_terms.setdefault(entity_name, {})

        def _merge_items(items: list[dict[str, Any]] | None, polarity: str) -> None:
            if not items:
                return
            for it in items:
                if not isinstance(it, dict):
                    continue
                term = (it.get("text") or "").strip()
                if not term:
                    continue
                try:
                    m = int(it.get("mentions") or 0)
                except Exception:
                    m = 0
                if m <= 0:
                    continue

                term_counts[term] = term_counts.get(term, 0) + m
                rec = per.setdefault(term, {"pos": 0, "neg": 0, "platform_dist": {}, "keyword_dist": {}})
                if polarity == "pos":
                    rec["pos"] += m
                else:
                    rec["neg"] += m

                p_dist = it.get("platform_distribution") or {}
                k_dist = it.get("keyword_distribution") or {}
                if isinstance(p_dist, dict):
                    for k, v in p_dist.items():
                        try:
                            vv = int(v or 0)
                        except Exception:
                            vv = 0
                        if vv:
                            rec["platform_dist"][k] = int(rec["platform_dist"].get(k, 0)) + vv
                if isinstance(k_dist, dict):
                    for k, v in k_dist.items():
                        try:
                            vv = int(v or 0)
                        except Exception:
                            vv = 0
                        if vv:
                            rec["keyword_dist"][k] = int(rec["keyword_dist"].get(k, 0)) + vv

        _merge_items(e.get("top_features"), "pos")
        _merge_items(e.get("top_issues"), "neg")

    if not term_counts:
        return {"status": "skipped", "reason": "no_entity_terms"}

    llm_used = False
    token_stats: dict[str, Any] | None = None
    clusters: list[dict[str, Any]] = []
    try:
        llm_input = format_terms_for_llm(term_counts, top_k=top_terms_for_llm)
        if llm_input.strip():
            chain = create_attribute_normalization_chain()
            resp, stats = invoke_chain_with_stats_sync(chain, {"attributes": llm_input}, "chat")
            text = resp.content if hasattr(resp, "content") else str(resp)
            clusters = parse_normalization_response(text)
            if clusters:
                llm_used = True
                token_stats = stats
    except Exception as e:
        logger.error(f"[Snapshot Stage2] LLM clustering failed: {e}", exc_info=True)

    if not clusters:
        clusters = fallback_cluster_terms(term_counts)

    term_to_cluster = build_term_to_cluster(clusters)
    cluster_names = [c.get("name") for c in clusters if isinstance(c, dict) and c.get("name")]

    cluster_stats: dict[str, dict[str, Any]] = {}
    for raw_term, cnt in term_counts.items():
        cname = term_to_cluster.get(raw_term, raw_term)
        st = cluster_stats.setdefault(cname, {"mentions": 0})
        st["mentions"] += cnt

    entity_matrix: list[dict[str, Any]] = []
    for entity_name, terms in entity_terms.items():
        dim_map: dict[str, dict[str, Any]] = {}
        for raw_term, rec in terms.items():
            cname = term_to_cluster.get(raw_term, raw_term)
            cell = dim_map.setdefault(cname, {
                "mentions": 0,
                "pos": 0,
                "neg": 0,
                "sentiment": 0.0,
                "platform_distribution": defaultdict(int),
                "keyword_distribution": defaultdict(int),
                "raw_terms": [],
            })
            pos = int(rec.get("pos") or 0)
            neg = int(rec.get("neg") or 0)
            cell["mentions"] += pos + neg
            cell["pos"] += pos
            cell["neg"] += neg
            cell["raw_terms"].append(raw_term)
            for k, v in (rec.get("platform_dist") or {}).items():
                cell["platform_distribution"][k] += int(v or 0)
            for k, v in (rec.get("keyword_dist") or {}).items():
                cell["keyword_distribution"][k] += int(v or 0)

        for _, cell in dim_map.items():
            total = int(cell["mentions"] or 0)
            if total > 0:
                cell["sentiment"] = round((float(cell["pos"]) - float(cell["neg"])) / float(total), 2)
            cell["platform_distribution"] = dict(cell["platform_distribution"])
            cell["keyword_distribution"] = dict(cell["keyword_distribution"])

        entity_matrix.append({"entity": entity_name, "dimensions": dim_map})

    sorted_dims = sorted(cluster_stats.items(), key=lambda x: x[1].get("mentions", 0), reverse=True)
    top_dimensions = [name for name, _ in sorted_dims[:12]]

    return {
        "status": "completed",
        "llm": {"used": llm_used, "token_stats": token_stats},
        "drivers": {
            "min_cell_mentions": min_cell_mentions,
            "dimensions_top": top_dimensions,
            "dimensions_all": cluster_names,
            "dimension_stats": {k: v for k, v in sorted_dims},
            "entity_matrix": entity_matrix,
        },
    }


