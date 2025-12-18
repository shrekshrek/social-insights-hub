"""项目级手动快照（多任务合并聚合）

目标：基于任务级 analysis_result 做多维数据整合，支持全域声量、竞品对比和来源追溯。
"""

from __future__ import annotations

from collections import defaultdict, Counter
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
    task_data_list: list[dict[str, Any]],
    max_items: int = 60,
    max_post_ids_sample: int = 50,
) -> dict[str, Any]:
    """从多个任务的 analysis_result 生成项目级快照结果。

    Args:
        project_id: 项目ID
        included_task_ids: 参与合并的任务ID（用于 meta.scope）
        task_data_list: 包含上下文的任务数据列表，每项包含:
            - task_id: int
            - platform: str
            - keyword: str
            - analysis_result: dict
        max_items: entities/topics 的最大保留数量（按 score 排序）
        max_post_ids_sample: 每个条目保留的 (task_id, post_id) 样本数量
    """

    # 构建任务上下文映射
    task_context_map = {
        t["task_id"]: {
            "platform": t.get("platform", "unknown"),
            "keyword": t.get("keyword", ""),
        }
        for t in task_data_list
    }

    # ==================== 1. Overview & Volume Stats ====================
    total_volume = 0
    platform_volume = defaultdict(int)
    keyword_volume = defaultdict(int)
    task_diagnostics: list[dict[str, Any]] = []
    
    # 情感聚合 (用于计算加权平均)
    global_sentiment_sum = 0.0
    global_sentiment_count = 0

    # ==================== 2. Entity & Topic Buckets ====================
    entity_bucket: dict[str, dict[str, Any]] = {}
    topic_bucket: dict[str, dict[str, Any]] = {}
    
    # 维度聚合 (Aspect Analysis)
    aspect_bucket: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "heat": 0.0,
        "sentiment_sum": 0.0,
        "sentiment_weight": 0.0,
        "mention_count": 0,
        "keywords": defaultdict(int),
        "platforms": defaultdict(int),
        "top_terms": defaultdict(int)  # category 下的高频词
    })

    for task_data in task_data_list:
        tid = task_data["task_id"]
        result = task_data.get("analysis_result") or {}
        ctx = task_context_map.get(tid, {})
        platform = ctx.get("platform", "unknown")
        keyword = ctx.get("keyword", "unknown")

        # 1. Volume
        vol_data = (result.get("meta") or {}).get("data_volume") or {}
        count = vol_data.get("total", 0) or 0
        # 兜底：旧任务/异常任务 meta.data_volume 可能缺失
        if not isinstance(count, int):
            try:
                count = int(count)
            except Exception:
                count = 0
        if count <= 0:
            try:
                count = int(task_data.get("posts_count", 0) or 0)
            except Exception:
                count = 0
        total_volume += count
        platform_volume[platform] += count
        keyword_volume[keyword] += count
        
        # 2. Global Sentiment (from metrics.nsr)
        metrics = result.get("metrics") or {}
        nsr = metrics.get("nsr", 0.0)
        # 简单加权：假设NSR代表该任务所有帖子的平均情感
        global_sentiment_sum += nsr * count
        global_sentiment_count += count

        # 3. Entities Aggregation
        # 规范口径：项目级快照只使用 canonical 字段 aggregated_entities，不使用 insights 兜底
        raw_agg_entities = result.get("aggregated_entities")
        raw_insights_entities = (result.get("insights") or {}).get("top_entities")
        raw_agg_entities_list = raw_agg_entities if isinstance(raw_agg_entities, list) else []
        raw_insights_entities_list = raw_insights_entities if isinstance(raw_insights_entities, list) else []

        if raw_agg_entities_list:
            entities: list[dict[str, Any]] = raw_agg_entities_list
            used_entities_source = "aggregated_entities"
        else:
            entities = []
            used_entities_source = "none"
        for e in entities:
            name = (e or {}).get("name") or ""
            if not name:
                continue
            role = str((e or {}).get("role") or "").lower()
            etype = str((e or {}).get("type") or "")
            
            # Key 变更：不再包含 role 和 type，只按归一化后的名称聚合
            # 解决 "XPEL|brand" 和 "XPEL|product" 分裂的问题
            key = f"{normalize_name(name)}"

            bucket = entity_bucket.get(key)
            if not bucket:
                bucket = {
                    "name": name,
                    # 不再存储单一 role/type，而是用 Counter 统计众数
                    "role_counts": Counter(),
                    "type_counts": Counter(),
                    "category": (e or {}).get("category"),
                    "parent": (e or {}).get("parent"),
                    "heat": 0.0,
                    "mentions_set": set(),
                    "post_ids_sample": [],
                    "source_tasks": defaultdict(set),
                    "original_terms_counts": defaultdict(int),
                    # New: Distribution Fingerprints
                    "platform_dist": defaultdict(int),
                    "keyword_dist": defaultdict(int),
                }
                entity_bucket[key] = bucket
            
            # 累加 role 和 type 频次
            if role:
                bucket["role_counts"][role] += 1
            if etype:
                bucket["type_counts"][etype] += 1

            heat = float((e or {}).get("heat", 0.0) or 0.0)
            bucket["heat"] += heat

            # 记录分布（按 mentions 加权，更符合“贡献占比”语义）
            try:
                mentions_weight = int((e or {}).get("mentions") or 0)
            except Exception:
                mentions_weight = 0
            if mentions_weight <= 0:
                mentions_weight = len((e or {}).get("post_ids") or [])
            bucket["platform_dist"][platform] += mentions_weight
            bucket["keyword_dist"][keyword] += mentions_weight

            for pid in (e or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                bucket["mentions_set"].add((tid, pid_int))
                bucket["source_tasks"][tid].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append({"task_id": tid, "post_id": pid_int})

            _merge_original_terms(bucket["original_terms_counts"], (e or {}).get("original_terms"))

        # 4. Topics Aggregation
        # 规范口径：项目级快照只使用 canonical 字段 aggregated_opinions，不使用 insights 兜底
        raw_agg_opinions = result.get("aggregated_opinions")
        raw_insights_topics = (result.get("insights") or {}).get("top_topics")
        raw_agg_opinions_list = raw_agg_opinions if isinstance(raw_agg_opinions, list) else []
        raw_insights_topics_list = raw_insights_topics if isinstance(raw_insights_topics, list) else []

        if raw_agg_opinions_list:
            opinions: list[dict[str, Any]] = raw_agg_opinions_list
            used_opinions_source = "aggregated_opinions"
        else:
            opinions = []
            used_opinions_source = "none"
        for o in opinions:
            name = (o or {}).get("name") or ""
            if not name:
                continue
            category = (o or {}).get("category") or "其他"
            sentiment = (o or {}).get("sentiment") or 0.0
            try:
                mentions_weight = int((o or {}).get("mentions") or 0)
            except Exception:
                mentions_weight = 0
            if mentions_weight <= 0:
                mentions_weight = len((o or {}).get("post_ids") or [])
            
            # Key for unique topic
            key = f"{normalize_name(name)}|{category}" # 忽略 sentiment 差异进行合并，计算平均情感
            
            bucket = topic_bucket.get(key)
            if not bucket:
                bucket = {
                    "name": name,
                    "category": category,
                    "heat": 0.0,
                    "sentiment_sum": 0.0,
                    "sentiment_weight": 0.0,
                    "mentions_set": set(),
                    "post_ids_sample": [],
                    "source_tasks": defaultdict(set),
                    "original_terms_counts": defaultdict(int),
                    "platform_dist": defaultdict(int),
                    "keyword_dist": defaultdict(int),
                }
                topic_bucket[key] = bucket

            heat = float((o or {}).get("heat", 0.0) or 0.0)
            bucket["heat"] += heat
            bucket["sentiment_sum"] += float(sentiment) * float(mentions_weight)
            bucket["sentiment_weight"] += float(mentions_weight)

            bucket["platform_dist"][platform] += mentions_weight
            bucket["keyword_dist"][keyword] += mentions_weight
            
            # Aspect Aggregation
            asp = aspect_bucket[category]
            asp["heat"] += heat
            asp["sentiment_sum"] += float(sentiment) * float(mentions_weight)
            asp["sentiment_weight"] += float(mentions_weight)
            asp["mention_count"] += mentions_weight
            asp["keywords"][keyword] += mentions_weight
            asp["platforms"][platform] += mentions_weight
            asp["top_terms"][name] += mentions_weight

            for pid in (o or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                bucket["mentions_set"].add((tid, pid_int))
                bucket["source_tasks"][tid].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append({"task_id": tid, "post_id": pid_int})

            _merge_original_terms(bucket["original_terms_counts"], (o or {}).get("original_terms"))

        # 5. Diagnostics (帮助定位“为什么快照里某块为空”)
        task_diagnostics.append({
            "task_id": tid,
            "platform": platform,
            "keyword": keyword,
            "data_volume_total": count,
            "nsr": metrics.get("nsr"),
            "entities_count": len(entities),
            "opinions_count": len(opinions),
            "has_entities": len(entities) > 0,
            "has_opinions": len(opinions) > 0,
            "has_meta_keywords": bool(((result.get("meta") or {}).get("keywords") or [])),
            "raw_aggregated_entities_count": len(raw_agg_entities_list),
            "raw_insights_top_entities_count": len(raw_insights_entities_list),
            "used_entities_source": used_entities_source,
            "entities_sample": [
                (x or {}).get("name") for x in (entities[:3] if isinstance(entities, list) else []) if isinstance(x, dict)
            ],
            "raw_aggregated_opinions_count": len(raw_agg_opinions_list),
            "raw_insights_top_topics_count": len(raw_insights_topics_list),
            "used_opinions_source": used_opinions_source,
            "opinions_sample": [
                (x or {}).get("name") for x in (opinions[:3] if isinstance(opinions, list) else []) if isinstance(x, dict)
            ],
        })

    # ==================== Finalize Entities ====================
    project_entities: list[dict[str, Any]] = []
    for b in entity_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))
        
        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True)
        ]
        
        # Determine main role and type
        role_counts = b.get("role_counts", Counter())
        type_counts = b.get("type_counts", Counter())
        main_role = role_counts.most_common(1)[0][0] if role_counts else "unknown"
        main_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"

        project_entities.append({
            "name": b["name"],
            "role": main_role,
            "type": main_type,
            "category": b["category"],
            "parent": b["parent"],
            "heat": round(heat, 3),
            "mentions": mentions,
            "score": round(score, 3),
            "original_terms": [
                {"text": text, "count": count}
                for text, count in sorted(b["original_terms_counts"].items(), key=lambda x: x[1], reverse=True)
            ],
            "source_tasks": source_tasks,
            "post_ids_sample": b["post_ids_sample"],
            # Distributions
            "platform_distribution": dict(b["platform_dist"]),
            "keyword_distribution": dict(b["keyword_dist"]),
        })

    project_entities.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_entities = project_entities[:max_items]

    # ==================== Finalize Topics ====================
    project_topics: list[dict[str, Any]] = []
    for b in topic_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))
        avg_sentiment = b["sentiment_sum"] / b["sentiment_weight"] if b["sentiment_weight"] > 0 else 0.0

        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True)
        ]
        
        project_topics.append({
            "name": b["name"],
            "category": b["category"],
            "sentiment": round(avg_sentiment, 2),
            "heat": round(heat, 3),
            "mentions": mentions,
            "score": round(score, 3),
            "original_terms": [
                {"text": text, "count": count}
                for text, count in sorted(b["original_terms_counts"].items(), key=lambda x: x[1], reverse=True)
            ],
            "source_tasks": source_tasks,
            "post_ids_sample": b["post_ids_sample"],
             # Distributions
            "platform_distribution": dict(b["platform_dist"]),
            "keyword_distribution": dict(b["keyword_dist"]),
        })

    project_topics.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_topics = project_topics[:max_items]
    
    # ==================== Finalize Aspects ====================
    project_aspects = []
    for cat, data in aspect_bucket.items():
        avg_sent = data["sentiment_sum"] / data["sentiment_weight"] if data["sentiment_weight"] > 0 else 0.0
        project_aspects.append({
            "category": cat,
            "heat": round(data["heat"], 2),
            "sentiment": round(avg_sent, 2),
            "mention_count": data["mention_count"],
            "top_keywords": sorted(data["top_terms"].keys(), key=lambda k: data["top_terms"][k], reverse=True)[:5],
            "platform_distribution": dict(data["platforms"]),
            "keyword_distribution": dict(data["keywords"]),
        })
    project_aspects.sort(key=lambda x: x["heat"], reverse=True)

    # ==================== Finalize Overview ====================
    global_avg_sentiment = global_sentiment_sum / global_sentiment_count if global_sentiment_count > 0 else 0.0
    
    overview = {
        "total_volume": total_volume,
        "global_sentiment": round(global_avg_sentiment, 2),
        "platform_volume": dict(platform_volume),
        "keyword_volume": dict(keyword_volume),
    }

    return {
        "meta": {
            "project_id": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "mode": "selected_tasks",
                "included_task_ids": included_task_ids,
                "platforms": list(platform_volume.keys()),
                "keywords": list(keyword_volume.keys()),
            },
            "task_diagnostics": task_diagnostics,
        },
        "overview": overview,
        "topic_aspects": project_aspects,
        "details": {
            "top_entities": project_entities,
            "top_topics": project_topics,
        },
        # 保持旧结构兼容性（可选）
        "insights": {
            "project_top_entities": project_entities,
            "project_top_topics": project_topics,
        },
    }
