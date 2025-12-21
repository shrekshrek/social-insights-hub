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


def _empty_quadrant_summary() -> dict[str, int]:
    return {
        "Q1_danger": 0,
        "Q2_brand": 0,
        "Q3_complaint": 0,
        "Q4_niche": 0,
        "neutral": 0,
    }


def _compute_quadrant_label(sentiment: float, cii: float, avg_cii: float) -> str:
    """项目级四象限标签（按全局 avg_cii 统一口径重算）"""
    if sentiment < -0.5 and cii > avg_cii:
        return "Q1_danger"
    if sentiment > 0.5 and cii > avg_cii:
        return "Q2_brand"
    if sentiment < -0.5 and cii <= avg_cii:
        return "Q3_complaint"
    if sentiment > 0.5 and cii <= avg_cii:
        return "Q4_niche"
    return "neutral"


def _ensure_attr_bucket() -> dict[str, Any]:
    return {
        "items": defaultdict(lambda: {
            "mentions_set": set(),  # set[(task_id, post_id)]
            "post_ids_sample": [],
            "original_terms_counts": defaultdict(int),
            "platform_dist": defaultdict(int),
            "keyword_dist": defaultdict(int),
        })
    }


def _merge_entity_attr_items(
    *,
    bucket: dict[str, Any],
    tid: int,
    platform: str,
    keyword: str,
    attr_name: str,
    attr_items: list[dict[str, Any]] | None,
    max_post_ids_sample: int,
) -> None:
    """把任务级 entity.{features/issues/...} 合并进项目级 bucket。

    任务级结构（见 entity_aggregation.py）：
      - [{ "text": str, "post_ids": [int], "original_terms"?: [{"text": str, "count": int}] }]
    """
    if not attr_items:
        return
    if "attr_buckets" not in bucket:
        bucket["attr_buckets"] = {
            "features": _ensure_attr_bucket(),
            "issues": _ensure_attr_bucket(),
            "expectations": _ensure_attr_bucket(),
            "audience": _ensure_attr_bucket(),
            "scenarios": _ensure_attr_bucket(),
            "market_factors": _ensure_attr_bucket(),
            "competitors": _ensure_attr_bucket(),
        }
    if attr_name not in bucket["attr_buckets"]:
        bucket["attr_buckets"][attr_name] = _ensure_attr_bucket()

    items_dict = bucket["attr_buckets"][attr_name]["items"]

    for it in attr_items:
        text = (it or {}).get("text") or ""
        if not text:
            continue

        sub = items_dict[text]
        post_ids = (it or {}).get("post_ids") or []
        post_ids_int: list[int] = []
        for pid in post_ids:
            try:
                post_ids_int.append(int(pid))
            except Exception:
                continue

        # mentions_weight：用唯一帖子数口径（属性维度最稳）
        mentions_weight = len(set(post_ids_int))
        if mentions_weight <= 0:
            continue

        sub["platform_dist"][platform] += mentions_weight
        sub["keyword_dist"][keyword] += mentions_weight

        for pid_int in set(post_ids_int):
            sub["mentions_set"].add((tid, pid_int))
            if len(sub["post_ids_sample"]) < max_post_ids_sample:
                sub["post_ids_sample"].append({"task_id": tid, "post_id": pid_int})

        _merge_original_terms(sub["original_terms_counts"], (it or {}).get("original_terms"))


def build_project_snapshot_result(
    *,
    project_id: int,
    included_task_ids: list[int],
    task_data_list: list[dict[str, Any]],
    max_items: int = 200,
    max_post_ids_sample: int = 50,
    subject: str | None = None,
    competitors: list[str] | None = None,
    platform_weights: dict[str, float] | None = None,
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
        max_items: details.top_entities / details.top_topics 的候选池数量（按 score 排序）
          - 推荐：200（用于后续“先归一再截断 Top60”的流程）
        max_post_ids_sample: 每个条目保留的 (task_id, post_id) 样本数量
        subject: 主体品牌/产品（用于 Focus 层触发与角色仲裁；为空则跳过 Focus）
        competitors: 竞品列表（用于角色仲裁与 Focus 层对比）
        platform_weights: 平台权重覆盖（key=platform code，value=权重系数）
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

    # ==================== 2.1 Project-level Quadrant Points (recompute with global threshold) ====================
    quadrant_points_raw: list[dict[str, Any]] = []
    quadrant_total_cii = 0.0
    quadrant_count = 0
    
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

        # 0. Project-level Quadrant: reuse points but recompute labels later with global avg_cii
        charts = result.get("charts") or {}
        raw_quadrant = charts.get("quadrant") or []
        if isinstance(raw_quadrant, list) and raw_quadrant:
            for p in raw_quadrant:
                try:
                    x = float((p or {}).get("x"))
                    y = float((p or {}).get("y"))
                except Exception:
                    continue
                post_id = (p or {}).get("post_id")
                try:
                    post_id_int = int(post_id)
                except Exception:
                    continue
                quadrant_points_raw.append({
                    "task_id": tid,
                    "post_id": post_id_int,
                    "x": x,
                    "y": y,
                    "label": (p or {}).get("label") or "",
                    "platform": platform,
                    "keyword": keyword,
                })
                quadrant_total_cii += y
                quadrant_count += 1

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
                    # New: aggregated attributes (features/issues/...)
                    "attr_buckets": {
                        "features": _ensure_attr_bucket(),
                        "issues": _ensure_attr_bucket(),
                        "expectations": _ensure_attr_bucket(),
                        "audience": _ensure_attr_bucket(),
                        "scenarios": _ensure_attr_bucket(),
                        "market_factors": _ensure_attr_bucket(),
                        "competitors": _ensure_attr_bucket(),
                    },
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

            # 3.x Entity Attribute Aggregation (Stage 1)
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="features",
                attr_items=(e or {}).get("features"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="issues",
                attr_items=(e or {}).get("issues"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="expectations",
                attr_items=(e or {}).get("expectations"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="audience",
                attr_items=(e or {}).get("audience"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="scenarios",
                attr_items=(e or {}).get("scenarios"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="market_factors",
                attr_items=(e or {}).get("market_factors"),
                max_post_ids_sample=max_post_ids_sample,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="competitors",
                attr_items=(e or {}).get("competitors"),
                max_post_ids_sample=max_post_ids_sample,
            )

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

        def _finalize_attr(attr_name: str, top_k: int = 10) -> list[dict[str, Any]]:
            attr_bucket = (b.get("attr_buckets") or {}).get(attr_name) or {}
            items_dict = (attr_bucket.get("items") or {})
            items_list = []
            for text, sub in items_dict.items():
                mentions_attr = len(sub.get("mentions_set") or [])
                if mentions_attr <= 0:
                    continue
                items_list.append({
                    "text": text,
                    "mentions": mentions_attr,
                    "original_terms": [
                        {"text": ot, "count": cnt}
                        for ot, cnt in sorted((sub.get("original_terms_counts") or {}).items(), key=lambda x: x[1], reverse=True)
                    ],
                    "post_ids_sample": sub.get("post_ids_sample") or [],
                    "platform_distribution": dict(sub.get("platform_dist") or {}),
                    "keyword_distribution": dict(sub.get("keyword_dist") or {}),
                })
            items_list.sort(key=lambda x: x.get("mentions", 0), reverse=True)
            return items_list[:top_k]

        project_entities.append({
            "name": b["name"],
            "role": main_role,
            "type": main_type,
            # breakdowns (for mixed cases like XPEL brand/product)
            "role_breakdown": dict(role_counts),
            "type_breakdown": dict(type_counts),
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
            # Aggregated attributes (Stage 1)
            "top_features": _finalize_attr("features"),
            "top_issues": _finalize_attr("issues"),
            "top_expectations": _finalize_attr("expectations"),
            "top_audience": _finalize_attr("audience"),
            "top_scenarios": _finalize_attr("scenarios"),
            "top_market_factors": _finalize_attr("market_factors"),
            "top_competitors": _finalize_attr("competitors"),
        })

    project_entities.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_entities = project_entities[:max_items]

    # ==================== Finalize Project Entity Graph (TopN + threshold + platform/keyword breakdown) ====================
    # 说明：这是“实体-实体”的项目级共现网络，用于竞争格局总览；不同于任务级 context_graph（中心星图）。
    graph_top_n = 30
    graph_min_co_occurrence = 2

    # 从 entity_bucket 选取 TopN（按项目级 score）
    entity_candidates = []
    for k, b in entity_bucket.items():
        mentions_k = len(b["mentions_set"])
        if mentions_k <= 0:
            continue
        heat_k = float(b["heat"])
        score_k = float(calculate_score(heat_k, mentions_k))
        entity_candidates.append((k, score_k, b))
    entity_candidates.sort(key=lambda x: x[1], reverse=True)
    entity_candidates = entity_candidates[:graph_top_n]

    graph_nodes = []
    mentions_sets: dict[str, set[tuple[int, int]]] = {}
    for k, score_k, b in entity_candidates:
        mentions_sets[k] = set(b["mentions_set"])
        role_counts = b.get("role_counts", Counter())
        type_counts = b.get("type_counts", Counter())
        main_role = role_counts.most_common(1)[0][0] if role_counts else "unknown"
        main_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
        graph_nodes.append({
            "id": k,
            "name": b["name"],
            "role": main_role,
            "type": main_type,
            "mentions": len(b["mentions_set"]),
            "heat": round(float(b["heat"]), 3),
            "score": round(float(score_k), 3),
            "platform_distribution": dict(b.get("platform_dist") or {}),
            "keyword_distribution": dict(b.get("keyword_dist") or {}),
        })

    # edges
    graph_edges = []
    node_ids = [n["id"] for n in graph_nodes]
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            a = node_ids[i]
            b = node_ids[j]
            s1 = mentions_sets.get(a) or set()
            s2 = mentions_sets.get(b) or set()
            if not s1 or not s2:
                continue
            # intersection
            inter = s1 & s2
            co = len(inter)
            if co < graph_min_co_occurrence:
                continue
            union = len(s1 | s2)
            jaccard = (co / union) if union > 0 else 0.0

            platform_dist = defaultdict(int)
            keyword_dist = defaultdict(int)
            for tid, _pid in inter:
                c = task_context_map.get(tid) or {}
                platform_dist[c.get("platform", "unknown")] += 1
                keyword_dist[c.get("keyword", "unknown")] += 1

            graph_edges.append({
                "source": a,
                "target": b,
                "co_occurrence": co,
                "jaccard": round(jaccard, 4),
                "value": round(jaccard, 4),
                "platform_distribution": dict(platform_dist),
                "keyword_distribution": dict(keyword_dist),
            })
    graph_edges.sort(key=lambda e: (e.get("co_occurrence", 0), e.get("jaccard", 0.0)), reverse=True)

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

    # ==================== Finalize Project Quadrant (global recompute) ====================
    quadrant_avg_cii = (quadrant_total_cii / quadrant_count) if quadrant_count > 0 else 0.0
    quadrant_points = []
    quadrant_summary = _empty_quadrant_summary()
    quadrant_summary_by_platform: dict[str, dict[str, int]] = defaultdict(_empty_quadrant_summary)
    quadrant_summary_by_keyword: dict[str, dict[str, int]] = defaultdict(_empty_quadrant_summary)

    for p in quadrant_points_raw:
        label = _compute_quadrant_label(float(p["x"]), float(p["y"]), float(quadrant_avg_cii))
        quadrant_summary[label] += 1
        quadrant_summary_by_platform[p.get("platform", "unknown")][label] += 1
        quadrant_summary_by_keyword[p.get("keyword", "unknown")][label] += 1
        quadrant_points.append({
            **p,
            "quadrant": label,
        })

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
            "subject": subject,
            "competitors": competitors or [],
            "weights_used": platform_weights or {},
            "scope": {
                "mode": "selected_tasks",
                "included_task_ids": included_task_ids,
                "platforms": list(platform_volume.keys()),
                "keywords": list(keyword_volume.keys()),
            },
            "task_diagnostics": task_diagnostics,
        },
        "overview": overview,
        "charts": {
            "quadrant": quadrant_points,
            "quadrant_summary": quadrant_summary,
            "quadrant_summary_by_platform": dict(quadrant_summary_by_platform),
            "quadrant_summary_by_keyword": dict(quadrant_summary_by_keyword),
            "quadrant_thresholds": {
                "avg_cii": round(float(quadrant_avg_cii), 4),
                "sentiment_negative": -0.5,
                "sentiment_positive": 0.5,
            },
            "entity_graph": {
                "nodes": graph_nodes,
                "edges": graph_edges,
                "params": {
                    "top_n": graph_top_n,
                    "min_co_occurrence": graph_min_co_occurrence,
                },
            },
        },
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
