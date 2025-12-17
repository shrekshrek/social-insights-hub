"""项目级手动快照（多任务合并聚合）

目标：不引入复杂字典/LLM，只基于任务级 analysis_result 中的 aggregated_* 做轻量合并，
快速生成“项目级地基”（top entities/topics + 证据追溯）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from src.social_media.analysis.celery_tasks.aggregation.utils import calculate_score, normalize_name


def _merge_original_terms(term_counts: dict[str, int], original_terms: list[dict[str, Any]] | None) -> None:
    if not original_terms:
        return
    for t in original_terms:
        text = (t or {}).get("text")
        if not text:
            continue
        try:
            count = int((t or {}).get("count", 0))
        except Exception:
            count = 0
        if count <= 0:
            continue
        term_counts[text] += count


def build_project_snapshot_result(
    *,
    project_id: int,
    included_task_ids: list[int],
    task_results: list[dict[str, Any]],
    max_items: int = 60,
    max_post_ids_sample: int = 50,
) -> dict[str, Any]:
    """从多个任务的 analysis_result 生成项目级快照结果。

    Args:
        project_id: 项目ID
        included_task_ids: 参与合并的任务ID（用于 meta.scope）
        task_results: 每个任务对应的 analysis_result（dict）
        max_items: entities/topics 的最大保留数量（按 score 排序）
        max_post_ids_sample: 每个条目保留的 (task_id, post_id) 样本数量
    """

    # ==================== 聚合实体 ====================
    entity_bucket: dict[str, dict[str, Any]] = {}
    for task_id, result in zip(included_task_ids, task_results):
        entities: list[dict[str, Any]] = (result or {}).get("aggregated_entities") or []
        for e in entities:
            name = (e or {}).get("name") or ""
            if not name:
                continue
            role = str((e or {}).get("role") or "").lower()
            etype = str((e or {}).get("type") or "")
            key = f"{normalize_name(name)}|{role}|{etype}"

            bucket = entity_bucket.get(key)
            if not bucket:
                bucket = {
                    "name": name,
                    "role": role or (e or {}).get("role"),
                    "type": etype or (e or {}).get("type"),
                    "category": (e or {}).get("category"),
                    "parent": (e or {}).get("parent"),
                    "heat": 0.0,
                    "mentions_set": set(),  # set[tuple[int,int]]
                    "post_ids_sample": [],
                    "source_tasks_set": set(),
                    "source_tasks": defaultdict(set),  # task_id -> set[post_id]
                    "original_terms_counts": defaultdict(int),
                }
                entity_bucket[key] = bucket

            # heat
            try:
                bucket["heat"] += float((e or {}).get("heat", 0.0) or 0.0)
            except Exception:
                pass

            # post_ids（任务级是 int 列表）
            for pid in (e or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                bucket["mentions_set"].add((task_id, pid_int))
                bucket["source_tasks_set"].add(task_id)
                bucket["source_tasks"][task_id].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append({"task_id": task_id, "post_id": pid_int})

            _merge_original_terms(bucket["original_terms_counts"], (e or {}).get("original_terms"))

    project_entities: list[dict[str, Any]] = []
    for b in entity_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))
        original_terms = [
            {"text": text, "count": count}
            for text, count in sorted(b["original_terms_counts"].items(), key=lambda x: x[1], reverse=True)
        ]
        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True)
        ]
        project_entities.append({
            "name": b["name"],
            "role": b["role"],
            "type": b["type"],
            "category": b["category"],
            "parent": b["parent"],
            "heat": round(heat, 3),
            "mentions": mentions,
            "score": round(score, 3),
            "original_terms": original_terms,
            "source_tasks": source_tasks,
            "post_ids_sample": b["post_ids_sample"],
        })

    project_entities.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_entities = project_entities[:max_items]

    # ==================== 聚合观点 ====================
    topic_bucket: dict[str, dict[str, Any]] = {}
    for task_id, result in zip(included_task_ids, task_results):
        opinions: list[dict[str, Any]] = (result or {}).get("aggregated_opinions") or []
        for o in opinions:
            name = (o or {}).get("name") or ""
            if not name:
                continue
            category = (o or {}).get("category") or ""
            sentiment = (o or {}).get("sentiment")
            key = f"{normalize_name(name)}|{category}|{sentiment}"

            bucket = topic_bucket.get(key)
            if not bucket:
                bucket = {
                    "name": name,
                    "category": category,
                    "sentiment": sentiment,
                    "heat": 0.0,
                    "mentions_set": set(),
                    "post_ids_sample": [],
                    "source_tasks": defaultdict(set),
                    "original_terms_counts": defaultdict(int),
                }
                topic_bucket[key] = bucket

            try:
                bucket["heat"] += float((o or {}).get("heat", 0.0) or 0.0)
            except Exception:
                pass

            for pid in (o or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                bucket["mentions_set"].add((task_id, pid_int))
                bucket["source_tasks"][task_id].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append({"task_id": task_id, "post_id": pid_int})

            _merge_original_terms(bucket["original_terms_counts"], (o or {}).get("original_terms"))

    project_topics: list[dict[str, Any]] = []
    for b in topic_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))
        original_terms = [
            {"text": text, "count": count}
            for text, count in sorted(b["original_terms_counts"].items(), key=lambda x: x[1], reverse=True)
        ]
        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True)
        ]
        project_topics.append({
            "name": b["name"],
            "category": b["category"],
            "sentiment": b["sentiment"],
            "heat": round(heat, 3),
            "mentions": mentions,
            "score": round(score, 3),
            "original_terms": original_terms,
            "source_tasks": source_tasks,
            "post_ids_sample": b["post_ids_sample"],
        })

    project_topics.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_topics = project_topics[:max_items]

    return {
        "meta": {
            "project_id": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "mode": "selected_tasks",
                "included_task_ids": included_task_ids,
            },
        },
        "insights": {
            "project_top_entities": project_entities,
            "project_top_topics": project_topics,
        },
    }


