from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.social_media.analysis.celery_tasks.aggregation.utils import are_similar

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_stage_state(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """确保 result_data 中存在 stage2/stage3 的基础结构。"""
    stage2 = result.get("stage2") if isinstance(result.get("stage2"), dict) else {}
    stage3 = result.get("stage3") if isinstance(result.get("stage3"), dict) else {}

    stage2.setdefault("status", "processing")
    stage2.setdefault("started_at", now_iso())
    stage2["updated_at"] = now_iso()
    stage2.setdefault("steps", {})
    # 产品口径：实体归一 / 观点归一 / 程序化衍生 / 全局LLM总分析
    for k in [
        "entity_normalization",
        "opinion_normalization",
        "derived_analysis",
        "summary",
    ]:
        step = (
            stage2["steps"].get(k) if isinstance(stage2["steps"].get(k), dict) else {}
        )
        step.setdefault("status", "pending")
        stage2["steps"][k] = step

    stage3.setdefault("status", "pending")
    stage3["updated_at"] = now_iso()

    result["stage2"] = stage2
    result["stage3"] = stage3
    return stage2, stage3


def set_step(stage2: dict[str, Any], step: str, status: str, **extra: Any) -> None:
    stage2.setdefault("steps", {})
    cur = (
        stage2["steps"].get(step) if isinstance(stage2["steps"].get(step), dict) else {}
    )
    cur["status"] = status
    if extra:
        cur.update(extra)
    stage2["steps"][step] = cur
    stage2["updated_at"] = now_iso()


def format_terms_for_llm(term_counts: dict[str, int], top_k: int = 160) -> str:
    items = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return "\n".join([f"- {t} ({c})" for t, c in items if t and c > 0])


def fallback_cluster_terms(
    term_counts: dict[str, int], threshold: float = 0.85
) -> list[dict[str, Any]]:
    """规则降级：按相似度聚类，输出与 parse_normalization_response 类似的结构"""
    terms = [
        t
        for t, c in sorted(term_counts.items(), key=lambda x: x[1], reverse=True)
        if t and c > 0
    ]
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
            if are_similar(canon, other, threshold=threshold):
                originals.append(other)
                used.add(other)
        clusters.append({"name": canon, "original_terms": originals})
    return clusters


def build_term_to_cluster(clusters: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for c in clusters:
        name = (c or {}).get("name") or ""
        if not name:
            continue
        for ot in (c or {}).get("original_terms") or []:
            if isinstance(ot, str) and ot:
                mapping[ot] = name
    return mapping


def fallback_alias_map(items: list[str], threshold: float = 0.9) -> dict[str, str]:
    """规则降级：把相似字符串映射到先出现的 canonical"""
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


def merge_attr_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """合并 entity.top_features/top_issues（按 text 累加 mentions 与分布）"""
    if not items:
        return []
    bucket: dict[str, dict[str, Any]] = {}
    max_post_ids_sample = 50
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
        b = bucket.setdefault(
            text,
            {
                "text": text,
                "mentions": 0,
                "organic_mentions": 0,
                "promo_mentions": 0,
                "platform_distribution": {},
                "keyword_distribution": {},
                "original_terms": [],
                "post_ids_sample": [],
                "_post_ids_set": set(),
            },
        )
        b["mentions"] += m
        try:
            b["organic_mentions"] += int(it.get("organic_mentions") or 0)
        except Exception:
            pass
        try:
            b["promo_mentions"] += int(it.get("promo_mentions") or 0)
        except Exception:
            pass
        for k, v in (it.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = (
                    int(b["platform_distribution"].get(k, 0)) + vv
                )
        for k, v in (it.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = (
                    int(b["keyword_distribution"].get(k, 0)) + vv
                )
        ots = it.get("original_terms") or []
        if isinstance(ots, list) and ots:
            b["original_terms"].extend(
                [x for x in ots if isinstance(x, dict) and x.get("text")]
            )
        # 关键：保留可追溯样本帖（用于 Focus/SWOT/Gap 下钻）
        refs = it.get("post_ids_sample") or []
        if isinstance(refs, list) and refs:
            for r in refs:
                if len(b["post_ids_sample"]) >= max_post_ids_sample:
                    break
                if not isinstance(r, dict):
                    continue
                try:
                    tid = int(r.get("task_id") or 0)
                    pid = int(r.get("post_id") or 0)
                except Exception:
                    continue
                if tid <= 0 or pid <= 0:
                    continue
                key = f"{tid}:{pid}"
                if key in b["_post_ids_set"]:
                    continue
                b["_post_ids_set"].add(key)
                b["post_ids_sample"].append({"task_id": tid, "post_id": pid})
    merged = list(bucket.values())
    for b in merged:
        b.pop("_post_ids_set", None)
    merged.sort(key=lambda x: x.get("mentions", 0), reverse=True)
    return merged[:10]


def merge_token_usage_stats(stats_list: list[dict[str, Any]]) -> dict[str, Any]:
    """合并多个 invoke_chain_with_stats_sync 产出的 token stats 为一个 token_usage 结构。

    目标：与任务级 AnalysisJob.token_usage 格式一致：{summary, call_details}
    """
    if not stats_list:
        return {
            "summary": {
                "total_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "total_cost_cny": 0.0,
                "total_duration_seconds": 0.0,
            },
            "call_details": [],
        }

    merged_summary = {
        "total_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_cost_cny": 0.0,
        "total_duration_seconds": 0.0,
    }
    merged_calls: list[dict[str, Any]] = []
    call_index = 0

    for st in stats_list:
        if not isinstance(st, dict):
            continue
        summary = st.get("summary") if isinstance(st.get("summary"), dict) else {}
        merged_summary["total_calls"] += int(summary.get("total_calls") or 0)
        merged_summary["total_input_tokens"] += int(
            summary.get("total_input_tokens") or 0
        )
        merged_summary["total_output_tokens"] += int(
            summary.get("total_output_tokens") or 0
        )
        merged_summary["total_tokens"] += int(summary.get("total_tokens") or 0)
        merged_summary["total_cost_cny"] += float(summary.get("total_cost_cny") or 0.0)
        merged_summary["total_duration_seconds"] += float(
            summary.get("total_duration_seconds") or 0.0
        )

        calls = (
            st.get("call_details") if isinstance(st.get("call_details"), list) else []
        )
        for c in calls:
            if not isinstance(c, dict):
                continue
            cc = dict(c)
            cc["call_index"] = call_index
            call_index += 1
            merged_calls.append(cc)

    # 平均项
    if merged_summary["total_calls"] > 0:
        merged_summary["avg_tokens_per_call"] = (
            merged_summary["total_tokens"] / merged_summary["total_calls"]
        )
        merged_summary["avg_cost_per_call"] = (
            merged_summary["total_cost_cny"] / merged_summary["total_calls"]
        )
    else:
        merged_summary["avg_tokens_per_call"] = 0
        merged_summary["avg_cost_per_call"] = 0.0

    return {"summary": merged_summary, "call_details": merged_calls}
