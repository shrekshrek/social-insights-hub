from __future__ import annotations

import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import invoke_chain_with_stats_sync
from src.social_media.analysis.celery_tasks.aggregation.utils import calculate_score, are_similar
from src.langchain.chains.category_normalization_chain import (
    create_category_normalization_chain,
    format_categories_for_normalization,
    parse_category_normalization_response,
)
from src.langchain.chains.opinion_normalization_chain import (
    create_opinion_normalization_chain,
    parse_normalization_response as parse_opinion_normalization_response,
)

from .utils import build_term_to_cluster, fallback_alias_map

logger = logging.getLogger(__name__)


def _program_cluster_terms(
    term_counts: dict[str, int],
    threshold: float = 0.9,
) -> tuple[dict[str, int], dict[str, str], dict[str, list[str]]]:
    """程序归一：按相似度预聚类，返回 rep->count, raw->rep, rep->members。"""
    items = sorted([(t, int(c or 0)) for t, c in (term_counts or {}).items() if t], key=lambda x: x[1], reverse=True)
    reps: list[str] = []
    rep_counts: dict[str, int] = {}
    raw_to_rep: dict[str, str] = {}
    rep_members: dict[str, list[str]] = {}

    for t, c in items:
        assigned = None
        for r in reps:
            if are_similar(r, t, threshold=threshold):
                assigned = r
                break
        if assigned is None:
            reps.append(t)
            assigned = t
        raw_to_rep[t] = assigned
        rep_counts[assigned] = rep_counts.get(assigned, 0) + c
        rep_members.setdefault(assigned, []).append(t)

    return rep_counts, raw_to_rep, rep_members


def _format_opinions_for_llm(rep_counts: dict[str, int], rep_members: dict[str, list[str]], top_k: int = 80) -> str:
    lines: list[str] = []
    for rep, cnt in sorted(rep_counts.items(), key=lambda x: x[1], reverse=True)[:top_k]:
        members = rep_members.get(rep) or []
        extras = [m for m in members if m != rep]
        hint = f" [同义候选: {', '.join(extras[:8])}]" if extras else ""
        lines.append(f"- {rep} ({cnt}){hint}")
    return "\n".join(lines)


def _align_categories_for_topics(
    top_topics: list[dict[str, Any]],
    *,
    llm_threshold: int = 5,  # 任务级经验：类别过少时无需对齐
) -> dict[str, Any]:
    """观点归一的内置子步骤：类目对齐（LLM 优先，失败降级）。"""
    # count categories (weighted by mentions)
    category_counts: dict[str, int] = {}
    for t in top_topics or []:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category") or "").strip() or "其他"
        try:
            w = int(t.get("mentions") or 0)
        except Exception:
            w = 0
        if w <= 0:
            w = 1
        category_counts[cat] = category_counts.get(cat, 0) + w

    category_map: dict[str, str] = {}
    llm_used = False
    token_stats: dict[str, Any] | None = None

    try:
        if len(category_counts) > llm_threshold:
            formatted = format_categories_for_normalization(category_counts)
            if formatted.strip():
                chain = create_category_normalization_chain()
                resp, stats = invoke_chain_with_stats_sync(chain, {"categories": formatted}, "chat")
                text = resp.content if hasattr(resp, "content") else str(resp)
                category_map = parse_category_normalization_response(text) or {}
                if category_map:
                    llm_used = True
                    token_stats = stats
    except Exception as e:
        logger.error(f"[Snapshot Opinion] Category alignment failed: {e}", exc_info=True)

    def map_category(cat: str) -> str:
        cat = (cat or "").strip() or "其他"
        return (category_map.get(cat) or cat).strip() or "其他"

    topics_for_norm: list[dict[str, Any]] = []
    for t in top_topics or []:
        if not isinstance(t, dict):
            continue
        nm = (t.get("name") or "").strip()
        if not nm:
            continue
        topics_for_norm.append({**t, "category_aligned": map_category((t.get("category") or "").strip() or "其他")})

    return {
        "used": llm_used,
        "token_stats": token_stats,
        "category_map": category_map,
        "topics_for_norm": topics_for_norm,
    }


def normalize_opinion_aliases_by_category(
    *,
    top_topics: list[dict[str, Any]],
) -> dict[str, Any]:
    """观点归一：类目对齐（内置）→ 程序预聚类 → 按类目分组 LLM 归一（失败降级）。"""
    # 1) 内置类目对齐
    cat = _align_categories_for_topics(top_topics)
    topics_for_norm = cat.get("topics_for_norm") or []

    topic_llm_used = False
    token_stats_list: list[dict[str, Any]] = []
    topic_mapping_by_category: dict[str, dict[str, str]] = {}
    program_mapping_by_category: dict[str, dict[str, str]] = {}

    grouped: dict[str, dict[str, int]] = {}
    for t in topics_for_norm or []:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category_aligned") or "其他").strip() or "其他"
        nm = (t.get("name") or "").strip()
        if not nm:
            continue
        try:
            w = int(t.get("mentions") or 0)
        except Exception:
            w = 0
        if w <= 0:
            w = 1
        grouped.setdefault(cat, {})
        grouped[cat][nm] = grouped[cat].get(nm, 0) + w

    for cat, mp in grouped.items():
        # 候选池来自快照 top_topics（建议 200），这里按类目控制送入归一化的上限
        top_terms = dict(sorted(mp.items(), key=lambda x: x[1], reverse=True)[:100])
        # 程序预聚类（降噪/降 token）
        rep_counts, raw_to_rep, rep_members = _program_cluster_terms(top_terms)
        program_mapping_by_category[cat] = raw_to_rep
        try:
            chain = create_opinion_normalization_chain()
            formatted = _format_opinions_for_llm(rep_counts, rep_members, top_k=100)
            resp, stats = invoke_chain_with_stats_sync(chain, {"category": cat, "opinions": formatted}, "chat")
            text = resp.content if hasattr(resp, "content") else str(resp)
            clusters = parse_opinion_normalization_response(text)
            if clusters:
                m = build_term_to_cluster(clusters)
                # 补全：把程序聚类成员也映射到 canonical（避免 LLM 漏掉）
                full_map: dict[str, str] = {}
                for raw, rep in raw_to_rep.items():
                    full_map[raw] = m.get(raw) or m.get(rep) or rep
                topic_mapping_by_category[cat] = full_map
                topic_llm_used = True
                if stats:
                    token_stats_list.append(stats)
                continue
        except Exception as e:
            logger.error(f"[Snapshot Stage2] Topic alias normalization failed: {e}", exc_info=True)

        # fallback：直接使用程序预聚类映射（或最简单映射）
        if raw_to_rep:
            topic_mapping_by_category[cat] = raw_to_rep
        else:
            topic_mapping_by_category[cat] = fallback_alias_map(list(top_terms.keys()))

    return {
        "used": topic_llm_used,
        "category_alignment": {
            "used": bool(cat.get("used")),
            "token_stats": cat.get("token_stats"),
            "category_map": cat.get("category_map") or {},
        },
        "topics_for_norm": topics_for_norm,
        "token_stats_list": token_stats_list,
        "topic_mapping_by_category": topic_mapping_by_category,
        "program_mapping_by_category": program_mapping_by_category,
    }


def build_topics_aligned(
    *,
    topics_for_norm: list[dict[str, Any]],
    topic_mapping_by_category: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """根据 category_aligned + mapping 合并 topics_for_norm，产出对齐后的观点列表。"""
    bucket: dict[str, dict[str, Any]] = {}
    for t in topics_for_norm or []:
        if not isinstance(t, dict):
            continue
        raw_name = (t.get("name") or "").strip()
        cat = (t.get("category_aligned") or "其他").strip() or "其他"
        if not raw_name:
            continue
        canon = (topic_mapping_by_category.get(cat, {}) or {}).get(raw_name) or raw_name
        key = f"{cat}|{canon}"
        b = bucket.get(key)
        if not b:
            b = {
                "name": canon,
                "category": cat,
                "heat": 0.0,
                "mentions": 0,
                "sentiment_sum": 0.0,
                "sentiment_weight": 0.0,
                "platform_distribution": {},
                "keyword_distribution": {},
                "original_terms": [],
            }
            bucket[key] = b

        try:
            m = int(t.get("mentions") or 0)
        except Exception:
            m = 0
        if m <= 0:
            m = 1
        b["mentions"] += m
        b["heat"] += float(t.get("heat") or 0.0)
        try:
            s = float(t.get("sentiment") or 0.0)
        except Exception:
            s = 0.0
        b["sentiment_sum"] += s * float(m)
        b["sentiment_weight"] += float(m)

        for k, v in (t.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = int(b["platform_distribution"].get(k, 0)) + vv
        for k, v in (t.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = int(b["keyword_distribution"].get(k, 0)) + vv

        b["original_terms"].append(raw_name)

    aligned: list[dict[str, Any]] = []
    for _, b in bucket.items():
        avg_sent = (b["sentiment_sum"] / b["sentiment_weight"]) if b["sentiment_weight"] > 0 else 0.0
        score = float(calculate_score(float(b["heat"]), int(b["mentions"])))
        aligned.append({
            "name": b["name"],
            "category": b["category"],
            "heat": round(float(b["heat"]), 3),
            "mentions": int(b["mentions"]),
            "sentiment": round(float(avg_sent), 2),
            "score": round(float(score), 3),
            "platform_distribution": b["platform_distribution"],
            "keyword_distribution": b["keyword_distribution"],
            "original_terms": [{"text": x, "count": 1} for x in sorted(set(b["original_terms"]))],
        })
    aligned.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return aligned


