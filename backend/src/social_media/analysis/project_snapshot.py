"""项目级手动快照（多任务合并聚合）

目标：基于任务级 analysis_result 做多维数据整合，支持全域声量、竞品对比和来源追溯。
"""

from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Any

from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score,
    normalize_name,
)


def _normalize_platform_code(code: str) -> str:
    """将用户输入/文档名映射为系统内部平台 code（Platform.code）。

    系统内部约定（见 projects/init_data.py）：7 个平台
    - bili, dy, ks, tieba, wb, xhs, zhihu
    文档/用户可能输入全称：douyin/weibo/bilibili/kuaishou/xiaohongshu 等。
    """
    c = (code or "").strip().lower()
    if not c:
        return ""
    alias = {
        # internal codes (保持不变)
        "xhs": "xhs",
        "dy": "dy",
        "bili": "bili",
        "wb": "wb",
        "ks": "ks",
        "tieba": "tieba",
        "zhihu": "zhihu",
        # common full names -> internal codes
        "xiaohongshu": "xhs",
        "douyin": "dy",
        "bilibili": "bili",
        "weibo": "wb",
        "kuaishou": "ks",
    }
    return alias.get(c, c)


def _merge_original_terms(
    term_counts: dict[str, int], original_terms: list[dict[str, Any]] | None
) -> None:
    if not original_terms:
        return
    for t in original_terms:
        text = (t or {}).get("text")
        if not text:
            continue
        # 工程防御：限制单条原话长度，避免 token/内存膨胀
        text = str(text).strip()
        if not text:
            continue
        if len(text) > 100:
            text = text[:100]
        try:
            count = int((t or {}).get("count", 0))
        except Exception:
            count = 0
        if count <= 0:
            continue
        term_counts[text] += count


def _compute_spam_dist_4d_by_key(
    post_source_keys: set[str],
    comment_source_keys: set[str],
    spam_map_by_key: dict[str, str],
) -> dict[str, dict[str, int]] | None:
    """计算 4 维 spam 分布 (高/低广告 × 原文/评论)，基于 post_key 而非 post_id。

    与 spam_distribution.py:_compute_spam_dist_4d 逻辑相同，但操作 post_key (str)。
    """
    high_post = 0
    high_comment = 0
    low_post = 0
    low_comment = 0
    found = False

    for pk in post_source_keys:
        group = spam_map_by_key.get(pk)
        if group is not None:
            found = True
            if group == "high":
                high_post += 1
            else:
                low_post += 1

    for pk in comment_source_keys:
        group = spam_map_by_key.get(pk)
        if group is not None:
            found = True
            if group == "high":
                high_comment += 1
            else:
                low_comment += 1

    if not found:
        return None

    return {
        "high_spam": {
            "total": high_post + high_comment,
            "post": high_post,
            "comment": high_comment,
        },
        "low_spam": {
            "total": low_post + low_comment,
            "post": low_post,
            "comment": low_comment,
        },
    }


def _ensure_attr_bucket() -> dict[str, Any]:
    return {
        "items": defaultdict(
            lambda: {
                # 项目级去重口径：按 platform:post_id_on_platform 去重
                "mentions_set": set(),  # set[str] (post_key)
                "post_ids_sample": [],
                "original_terms_counts": defaultdict(int),
                "platform_dist": defaultdict(int),
                "keyword_dist": defaultdict(int),
                # 有机/推广提及计数（基于 spam_map_by_key）
                "organic_mentions_count": 0,
                "promo_mentions_count": 0,
            }
        )
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
    post_key_by_id: dict[int, str],
    post_info_by_key: dict[str, dict[str, Any]],
    primary_keyword_by_key: dict[str, str],
    primary_task_by_key: dict[str, int],
    spam_map_by_key: dict[str, str],
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
        # 项目级去重：把内部 post_id 映射为 post_key（platform:post_id_on_platform）
        post_ids = (it or {}).get("post_ids") or []
        pk_to_pid: dict[str, int] = {}
        for pid in post_ids:
            try:
                pid_int = int(pid)
            except Exception:
                continue
            pk = post_key_by_id.get(pid_int)
            if not pk:
                continue
            if pk not in pk_to_pid:
                pk_to_pid[pk] = pid_int

        # mentions_weight：用去重后的唯一帖子数口径（避免跨任务重复贴放大）
        mentions_weight = len(pk_to_pid)
        if mentions_weight <= 0:
            continue

        for pk, pid_int in pk_to_pid.items():
            if pk in sub["mentions_set"]:
                continue
            sub["mentions_set"].add(pk)
            info = post_info_by_key.get(pk) or {}
            sub["platform_dist"][str(info.get("platform") or platform)] += 1
            sub["keyword_dist"][str(primary_keyword_by_key.get(pk) or keyword)] += 1
            spam_group = spam_map_by_key.get(pk)
            if spam_group == "low":
                sub["organic_mentions_count"] += 1
            elif spam_group == "high":
                sub["promo_mentions_count"] += 1
            if len(sub["post_ids_sample"]) < max_post_ids_sample:
                sub["post_ids_sample"].append(
                    {
                        "task_id": int(primary_task_by_key.get(pk) or tid),
                        "post_id": pid_int,
                    }
                )

        _merge_original_terms(
            sub["original_terms_counts"], (it or {}).get("original_terms")
        )


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
    post_key_by_id: dict[int, str] | None = None,
    post_info_by_key: dict[str, dict[str, Any]] | None = None,
    primary_keyword_by_key: dict[str, str] | None = None,
    primary_task_by_key: dict[str, int] | None = None,
    spam_threshold: float = 6.0,
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
        post_key_by_id: {SocialPost.id -> "platform_code:post_id_on_platform"} 映射（用于跨任务去重）
        post_info_by_key: {"platform_code:post_id_on_platform" -> post meta}（包含 raw_cii/published_at 等）
        primary_keyword_by_key: {post_key -> keyword_label} 去重后关键词主归属（首见原则）
        primary_task_by_key: {post_key -> task_id} 去重后任务主归属（首见原则）
    """
    post_key_by_id = post_key_by_id or {}
    post_info_by_key = post_info_by_key or {}
    primary_keyword_by_key = primary_keyword_by_key or {}
    primary_task_by_key = primary_task_by_key or {}

    # 默认平台权重（可被覆盖）
    weights_used: dict[str, float] = {
        # 以系统内部 Platform.code 为准（xhs/dy/bili/wb）
        "bili": 1.5,
        "xhs": 1.0,
        "dy": 0.8,
        "wb": 0.6,
    }
    if isinstance(platform_weights, dict) and platform_weights:
        for k, v in platform_weights.items():
            try:
                kk = _normalize_platform_code(str(k))
                vv = float(v)
            except Exception:
                continue
            if not kk:
                continue
            weights_used[kk] = vv

    # 给 post_info 计算 normalized_heat（Raw_CII * weight）
    total_heat = 0.0
    for pk, info in list(post_info_by_key.items()):
        if not isinstance(info, dict):
            continue
        platform = _normalize_platform_code(str(info.get("platform") or "unknown"))
        try:
            raw_cii = float(info.get("raw_cii") or 0.0)
        except Exception:
            raw_cii = 0.0
        w = float(weights_used.get(platform, 1.0))
        info["weight"] = w
        info["normalized_heat"] = raw_cii * w
        info["platform"] = platform
        post_info_by_key[pk] = info
        total_heat += info["normalized_heat"]

    # 构建 spam_map_by_key：post_key → "high"/"low"
    spam_map_by_key: dict[str, str] = {}
    for pk, info in post_info_by_key.items():
        ss = info.get("spam_score")
        if ss is not None:
            spam_map_by_key[pk] = "high" if ss >= spam_threshold else "low"

    # 构建任务上下文映射
    task_context_map = {
        t["task_id"]: {
            "platform": t.get("platform", "unknown"),
            "keyword": t.get("keyword", ""),
        }
        for t in task_data_list
    }

    # 用“首见原则”填充 primary_keyword_by_key / primary_task_by_key（保证去重后关键词分布总和可控）
    # 说明：同一平台同一帖子可能出现在多个任务（不同关键词），此处选第一条作为主归属。
    for t in task_data_list:
        tid = t.get("task_id")
        ctx = task_context_map.get(tid, {})
        keyword = ctx.get("keyword", "unknown")
        ar = t.get("analysis_result") or {}
        # 从 entity/opinion 的 post_ids 收集 primary keyword/task
        for key_name in ["aggregated_entities", "aggregated_opinions"]:
            items = ar.get(key_name)
            if not isinstance(items, list):
                continue
            for it in items:
                for pid in (it or {}).get("post_ids") or []:
                    try:
                        pid_int = int(pid)
                    except Exception:
                        continue
                    pk = post_key_by_id.get(pid_int)
                    if not pk:
                        continue
                    if (
                        pk not in primary_keyword_by_key
                        or not primary_keyword_by_key.get(pk)
                    ):
                        primary_keyword_by_key[pk] = str(keyword or "unknown")
                    if pk not in primary_task_by_key or not primary_task_by_key.get(pk):
                        try:
                            primary_task_by_key[pk] = int(tid)
                        except Exception:
                            primary_task_by_key[pk] = 0

    # ==================== 1. Overview & Volume Stats ====================
    total_volume = 0
    platform_volume = defaultdict(int)
    keyword_volume = defaultdict(int)
    task_diagnostics: list[dict[str, Any]] = []

    # 情感聚合 (用于计算加权平均)
    global_sentiment_sum = 0.0
    global_sentiment_count = 0
    # 有机/推广情感聚合（来自 metrics.nsr_by_spam）
    organic_sentiment_sum = 0.0
    organic_sentiment_count = 0
    promo_sentiment_sum = 0.0
    promo_sentiment_count = 0

    # ==================== 2. Entity & Topic Buckets ====================
    entity_bucket: dict[str, dict[str, Any]] = {}
    topic_bucket: dict[str, dict[str, Any]] = {}

    # Step0 去重统计（基于 platform+post_id_on_platform）
    total_posts_raw = len(post_key_by_id)
    unique_posts = len(set(post_key_by_id.values())) if post_key_by_id else 0
    dedup_stats = {
        "total_posts_raw": total_posts_raw,
        "unique_posts": unique_posts,
        "duplicates_removed": max(total_posts_raw - unique_posts, 0),
        "dedup_key": "platform:post_id_on_platform",
    }

    # Step1 新鲜度统计（基于去重后的帖子集合）
    now = datetime.now(timezone.utc)
    last_7_days_count = 0
    last_30_days_count = 0
    ages: list[int] = []
    for pk, info in post_info_by_key.items():
        published_at = (info or {}).get("published_at")
        if not published_at:
            continue
        try:
            dt = published_at
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if getattr(dt, "tzinfo", None) is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = int((now - dt).days)
        except Exception:
            continue
        ages.append(age_days)
        if age_days <= 7:
            last_7_days_count += 1
        if age_days <= 30:
            last_30_days_count += 1
    freshness = {
        "last_7_days_count": last_7_days_count,
        "last_30_days_count": last_30_days_count,
        "avg_age_days": round(sum(ages) / len(ages), 1) if ages else 0.0,
    }

    # 维度聚合 (Aspect Analysis)
    aspect_bucket: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "heat": 0.0,
            "sentiment_sum": 0.0,
            "sentiment_weight": 0.0,
            "mention_count": 0,
            "keywords": defaultdict(int),
            "platforms": defaultdict(int),
            "top_terms": defaultdict(int),  # category 下的高频词
        }
    )

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
        # 有机/推广情感（来自 metrics.nsr_by_spam，按任务量加权）
        nsr_by_spam = metrics.get("nsr_by_spam")
        if isinstance(nsr_by_spam, dict):
            low_nsr = nsr_by_spam.get("low")
            high_nsr = nsr_by_spam.get("high")
            if low_nsr is not None and count > 0:
                try:
                    organic_sentiment_sum += float(low_nsr) * count
                    organic_sentiment_count += count
                except Exception:
                    pass
            if high_nsr is not None and count > 0:
                try:
                    promo_sentiment_sum += float(high_nsr) * count
                    promo_sentiment_count += count
                except Exception:
                    pass

        # 3. Entities Aggregation
        # 规范口径：项目级快照只使用 canonical 字段 aggregated_entities，不使用 insights 兜底
        raw_agg_entities = result.get("aggregated_entities")
        raw_insights_entities = (result.get("insights") or {}).get("top_entities")
        raw_agg_entities_list = (
            raw_agg_entities if isinstance(raw_agg_entities, list) else []
        )
        raw_insights_entities_list = (
            raw_insights_entities if isinstance(raw_insights_entities, list) else []
        )

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
            # parent 口径：沿用任务级 tags.parent（品牌用 "Self" 哨兵值；产品用品牌名；通用词为空）
            tags = (
                (e or {}).get("tags") if isinstance((e or {}).get("tags"), dict) else {}
            )
            parent_val = str((e or {}).get("parent") or "").strip()
            if not parent_val:
                parent_val = str((tags or {}).get("parent") or "").strip()
            if etype.strip().lower() == "brand" and not parent_val:
                parent_val = "Self"

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
                    "parent_counts": Counter(),
                    "category": (e or {}).get("category"),
                    "parent": "",
                    "heat": 0.0,  # normalized heat (Raw_CII * platform_weight) over deduped posts
                    "organic_heat": 0.0,  # heat from low_spam (organic) posts
                    "promo_heat": 0.0,  # heat from high_spam (promotional) posts
                    "mentions_set": set(),  # set[post_key]
                    "post_ids_sample": [],
                    "source_tasks": defaultdict(set),
                    "original_terms_counts": defaultdict(int),
                    # 情感聚合字段（用于行业象限散点图）
                    "sentiment_weighted_sum": 0.0,
                    "sentiment_weight": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "neutral_count": 0,
                    # 有机/推广情感分层（按 spam_distribution 权重）
                    "organic_sent_weighted_sum": 0.0,
                    "organic_sent_weight": 0.0,
                    "promo_sent_weighted_sum": 0.0,
                    "promo_sent_weight": 0.0,
                    # Spam 来源追踪（post_key 维度）
                    "post_source_keys": set(),
                    "comment_source_keys": set(),
                    # New: Distribution Fingerprints
                    "platform_dist": defaultdict(int),
                    "organic_platform_dist": defaultdict(int),
                    "promo_platform_dist": defaultdict(int),
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
            if parent_val:
                bucket["parent_counts"][parent_val] += 1

            # 累加 sentiment（从任务级实体中读取）
            entity_sentiment = (e or {}).get("sentiment")
            entity_mentions = len((e or {}).get("post_ids") or [])
            if entity_sentiment is not None and entity_mentions > 0:
                try:
                    sent_val = float(entity_sentiment)
                    bucket["sentiment_weighted_sum"] += sent_val * entity_mentions
                    bucket["sentiment_weight"] += entity_mentions
                except Exception:
                    pass
            # 累加情感分布
            sent_dist = (e or {}).get("sentiment_distribution")
            if isinstance(sent_dist, dict):
                try:
                    bucket["positive_count"] += int(sent_dist.get("positive") or 0)
                    bucket["negative_count"] += int(sent_dist.get("negative") or 0)
                    bucket["neutral_count"] += int(sent_dist.get("neutral") or 0)
                except Exception:
                    pass
            # 累加有机/推广情感（按任务级 spam_distribution 权重）
            task_spam_dist = (e or {}).get("spam_distribution")
            if isinstance(task_spam_dist, dict):
                low_total = int(
                    (task_spam_dist.get("low_spam") or {}).get("total") or 0
                )
                high_total = int(
                    (task_spam_dist.get("high_spam") or {}).get("total") or 0
                )
                organic_sent = (e or {}).get("organic_sentiment")
                promo_sent = (e or {}).get("promo_sentiment")
                if organic_sent is not None and low_total > 0:
                    try:
                        bucket["organic_sent_weighted_sum"] += (
                            float(organic_sent) * low_total
                        )
                        bucket["organic_sent_weight"] += low_total
                    except Exception:
                        pass
                if promo_sent is not None and high_total > 0:
                    try:
                        bucket["promo_sent_weighted_sum"] += (
                            float(promo_sent) * high_total
                        )
                        bucket["promo_sent_weight"] += high_total
                    except Exception:
                        pass

            # 构建任务级来源集合（用于 spam 4D 分布的 post/comment 归类）
            task_post_src: set[int] = set()
            task_comment_src: set[int] = set()
            for _src_pid in (e or {}).get("post_source_ids") or []:
                try:
                    task_post_src.add(int(_src_pid))
                except Exception:
                    pass
            for _src_pid in (e or {}).get("comment_source_ids") or []:
                try:
                    task_comment_src.add(int(_src_pid))
                except Exception:
                    pass

            # 去重后的 mentions 与 heat：按 post_key 聚合
            for pid in (e or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                pk = post_key_by_id.get(pid_int)
                if not pk:
                    continue
                if pk in bucket["mentions_set"]:
                    continue
                bucket["mentions_set"].add(pk)
                # Spam 来源归类（post vs comment）
                if pid_int in task_post_src:
                    bucket["post_source_keys"].add(pk)
                elif pid_int in task_comment_src:
                    bucket["comment_source_keys"].add(pk)
                else:
                    # 兜底：无来源信息时归入 post
                    bucket["post_source_keys"].add(pk)
                # heat 累加：normalized_heat（Raw_CII * platform_weight）
                info = post_info_by_key.get(pk) or {}
                try:
                    h = float(info.get("normalized_heat") or 0.0)
                    bucket["heat"] += h
                    spam_group = spam_map_by_key.get(pk)
                    if spam_group == "low":
                        bucket["organic_heat"] += h
                    elif spam_group == "high":
                        bucket["promo_heat"] += h
                except Exception:
                    pass
                # 分布：按去重后的主归属 keyword/platform 计数（总和=mentions）
                plat_key = str(info.get("platform") or platform)
                bucket["platform_dist"][plat_key] += 1
                if spam_group == "low":
                    bucket["organic_platform_dist"][plat_key] += 1
                elif spam_group == "high":
                    bucket["promo_platform_dist"][plat_key] += 1
                bucket["keyword_dist"][
                    str(primary_keyword_by_key.get(pk) or keyword)
                ] += 1
                # 仍保留样本 internal post_id 供前端追溯
                try:
                    primary_tid = int(primary_task_by_key.get(pk) or tid)
                except Exception:
                    primary_tid = tid
                bucket["source_tasks"][primary_tid].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append(
                        {"task_id": primary_tid, "post_id": pid_int}
                    )

            _merge_original_terms(
                bucket["original_terms_counts"], (e or {}).get("original_terms")
            )

            # 3.x Entity Attribute Aggregation (Stage 1)
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="features",
                attr_items=(e or {}).get("features"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="issues",
                attr_items=(e or {}).get("issues"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="expectations",
                attr_items=(e or {}).get("expectations"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="audience",
                attr_items=(e or {}).get("audience"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="scenarios",
                attr_items=(e or {}).get("scenarios"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="market_factors",
                attr_items=(e or {}).get("market_factors"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )
            _merge_entity_attr_items(
                bucket=bucket,
                tid=tid,
                platform=platform,
                keyword=keyword,
                attr_name="competitors",
                attr_items=(e or {}).get("competitors"),
                max_post_ids_sample=max_post_ids_sample,
                post_key_by_id=post_key_by_id,
                post_info_by_key=post_info_by_key,
                primary_keyword_by_key=primary_keyword_by_key,
                primary_task_by_key=primary_task_by_key,
                spam_map_by_key=spam_map_by_key,
            )

        # 4. Topics Aggregation
        # 规范口径：项目级快照只使用 canonical 字段 aggregated_opinions，不使用 insights 兜底
        raw_agg_opinions = result.get("aggregated_opinions")
        raw_insights_topics = (result.get("insights") or {}).get("top_topics")
        raw_agg_opinions_list = (
            raw_agg_opinions if isinstance(raw_agg_opinions, list) else []
        )
        raw_insights_topics_list = (
            raw_insights_topics if isinstance(raw_insights_topics, list) else []
        )

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
            # Key for unique topic
            key = f"{normalize_name(name)}|{category}"  # 忽略 sentiment 差异进行合并，计算平均情感

            bucket = topic_bucket.get(key)
            if not bucket:
                bucket = {
                    "name": name,
                    "category": category,
                    "heat": 0.0,  # normalized heat over deduped posts
                    "organic_heat": 0.0,  # heat from low_spam (organic) posts
                    "promo_heat": 0.0,  # heat from high_spam (promotional) posts
                    "sentiment_sum": 0.0,
                    "sentiment_weight": 0.0,
                    "mentions_set": set(),  # set[post_key]
                    "post_ids_sample": [],
                    "source_tasks": defaultdict(set),
                    "original_terms_counts": defaultdict(int),
                    "platform_dist": defaultdict(int),
                    "keyword_dist": defaultdict(int),
                    # Spam 来源追踪
                    "post_source_keys": set(),
                    "comment_source_keys": set(),
                    # 正/负极性计数（用于争议性检测）
                    "positive_mentions": 0,
                    "negative_mentions": 0,
                    # 有机/推广情感（按 spam_group 分层）
                    "organic_sent_sum": 0.0,
                    "organic_sent_w": 0.0,
                    "promo_sent_sum": 0.0,
                    "promo_sent_w": 0.0,
                }
                topic_bucket[key] = bucket

            # 构建任务级观点来源集合（用于 spam 4D 分布的 post/comment 归类）
            task_post_src_o: set[int] = set()
            task_comment_src_o: set[int] = set()
            for _src_pid in (o or {}).get("post_source_ids") or []:
                try:
                    task_post_src_o.add(int(_src_pid))
                except Exception:
                    pass
            for _src_pid in (o or {}).get("comment_source_ids") or []:
                try:
                    task_comment_src_o.add(int(_src_pid))
                except Exception:
                    pass

            for pid in (o or {}).get("post_ids") or []:
                try:
                    pid_int = int(pid)
                except Exception:
                    continue
                pk = post_key_by_id.get(pid_int)
                if not pk:
                    continue
                if pk in bucket["mentions_set"]:
                    continue
                bucket["mentions_set"].add(pk)
                # Spam 来源归类（post vs comment）
                if pid_int in task_post_src_o:
                    bucket["post_source_keys"].add(pk)
                elif pid_int in task_comment_src_o:
                    bucket["comment_source_keys"].add(pk)
                else:
                    bucket["post_source_keys"].add(pk)
                info = post_info_by_key.get(pk) or {}
                try:
                    h = float(info.get("normalized_heat") or 0.0)
                except Exception:
                    h = 0.0
                bucket["heat"] += h
                spam_group_t = spam_map_by_key.get(pk)
                if spam_group_t == "low":
                    bucket["organic_heat"] += h
                elif spam_group_t == "high":
                    bucket["promo_heat"] += h
                # sentiment：按 mentions（去重后帖子数）加权
                bucket["sentiment_sum"] += float(sentiment) * 1.0
                bucket["sentiment_weight"] += 1.0
                # 正/负极性计数（用于争议性检测）
                if float(sentiment) > 0:
                    bucket["positive_mentions"] += 1
                elif float(sentiment) < 0:
                    bucket["negative_mentions"] += 1
                # 有机/推广情感分层
                if spam_group_t == "low":
                    bucket["organic_sent_sum"] += float(sentiment)
                    bucket["organic_sent_w"] += 1.0
                elif spam_group_t == "high":
                    bucket["promo_sent_sum"] += float(sentiment)
                    bucket["promo_sent_w"] += 1.0

                # distributions（总和=mentions）
                bucket["platform_dist"][str(info.get("platform") or platform)] += 1
                bucket["keyword_dist"][
                    str(primary_keyword_by_key.get(pk) or keyword)
                ] += 1

                # Aspect Aggregation（按去重后的 mentions 计数）
                asp = aspect_bucket[category]
                asp["heat"] += h
                asp["sentiment_sum"] += float(sentiment) * 1.0
                asp["sentiment_weight"] += 1.0
                asp["mention_count"] += 1
                asp["keywords"][str(primary_keyword_by_key.get(pk) or keyword)] += 1
                asp["platforms"][str(info.get("platform") or platform)] += 1
                asp["top_terms"][name] += 1

                try:
                    primary_tid = int(primary_task_by_key.get(pk) or tid)
                except Exception:
                    primary_tid = tid
                bucket["source_tasks"][primary_tid].add(pid_int)
                if len(bucket["post_ids_sample"]) < max_post_ids_sample:
                    bucket["post_ids_sample"].append(
                        {"task_id": primary_tid, "post_id": pid_int}
                    )

            _merge_original_terms(
                bucket["original_terms_counts"], (o or {}).get("original_terms")
            )

        # 5. Diagnostics (帮助定位“为什么快照里某块为空”)
        task_diagnostics.append(
            {
                "task_id": tid,
                "platform": platform,
                "keyword": keyword,
                "data_volume_total": count,
                "nsr": metrics.get("nsr"),
                "entities_count": len(entities),
                "opinions_count": len(opinions),
                "has_entities": len(entities) > 0,
                "has_opinions": len(opinions) > 0,
                "has_meta_keywords": bool(
                    ((result.get("meta") or {}).get("keywords") or [])
                ),
                "raw_aggregated_entities_count": len(raw_agg_entities_list),
                "raw_insights_top_entities_count": len(raw_insights_entities_list),
                "used_entities_source": used_entities_source,
                "entities_sample": [
                    (x or {}).get("name")
                    for x in (entities[:3] if isinstance(entities, list) else [])
                    if isinstance(x, dict)
                ],
                "raw_aggregated_opinions_count": len(raw_agg_opinions_list),
                "raw_insights_top_topics_count": len(raw_insights_topics_list),
                "used_opinions_source": used_opinions_source,
                "opinions_sample": [
                    (x or {}).get("name")
                    for x in (opinions[:3] if isinstance(opinions, list) else [])
                    if isinstance(x, dict)
                ],
            }
        )

    # ==================== Finalize Entities ====================
    project_entities: list[dict[str, Any]] = []
    for b in entity_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))

        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(
                b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True
            )
        ]

        # Determine main role and type
        role_counts = b.get("role_counts", Counter())
        type_counts = b.get("type_counts", Counter())
        main_role = role_counts.most_common(1)[0][0] if role_counts else "unknown"
        main_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
        parent_counts = b.get("parent_counts", Counter())
        main_parent = parent_counts.most_common(1)[0][0] if parent_counts else ""

        def _finalize_attr(attr_name: str, top_k: int = 10) -> list[dict[str, Any]]:
            attr_bucket = (b.get("attr_buckets") or {}).get(attr_name) or {}
            items_dict = attr_bucket.get("items") or {}
            items_list = []
            for text, sub in items_dict.items():
                mentions_attr = len(sub.get("mentions_set") or [])
                if mentions_attr <= 0:
                    continue
                items_list.append(
                    {
                        "text": text,
                        "mentions": mentions_attr,
                        "organic_mentions": int(sub.get("organic_mentions_count") or 0),
                        "promo_mentions": int(sub.get("promo_mentions_count") or 0),
                        "original_terms": [
                            {"text": ot, "count": cnt}
                            for ot, cnt in sorted(
                                (sub.get("original_terms_counts") or {}).items(),
                                key=lambda x: (len(x[0] or ""), x[1]),
                                reverse=True,
                            )[:20]
                        ],
                        "post_ids_sample": sub.get("post_ids_sample") or [],
                        "platform_distribution": dict(sub.get("platform_dist") or {}),
                        "keyword_distribution": dict(sub.get("keyword_dist") or {}),
                    }
                )
            items_list.sort(key=lambda x: x.get("mentions", 0), reverse=True)
            return items_list[:top_k]

        # 计算加权平均情感值
        sentiment_weight = b.get("sentiment_weight") or 0
        if sentiment_weight > 0:
            avg_sentiment = round(b["sentiment_weighted_sum"] / sentiment_weight, 2)
        else:
            avg_sentiment = 0.0

        # 计算有机/推广情感
        organic_sentiment = None
        if (b.get("organic_sent_weight") or 0) > 0:
            organic_sentiment = round(
                b["organic_sent_weighted_sum"] / b["organic_sent_weight"], 2
            )
        promo_sentiment = None
        if (b.get("promo_sent_weight") or 0) > 0:
            promo_sentiment = round(
                b["promo_sent_weighted_sum"] / b["promo_sent_weight"], 2
            )

        # Spam 4D 分布
        spam_dist = _compute_spam_dist_4d_by_key(
            b["post_source_keys"], b["comment_source_keys"], spam_map_by_key
        )

        project_entities.append(
            {
                "name": b["name"],
                "role": main_role,
                "type": main_type,
                # breakdowns (for mixed cases like XPEL brand/product)
                "role_breakdown": dict(role_counts),
                "type_breakdown": dict(type_counts),
                "category": b["category"],
                "parent": main_parent,
                "heat": round(heat, 3),
                "organic_heat": round(float(b.get("organic_heat") or 0.0), 3),
                "promo_heat": round(float(b.get("promo_heat") or 0.0), 3),
                "mentions": mentions,
                "score": round(score, 3),
                # 情感字段（用于行业象限散点图）
                "sentiment": avg_sentiment,
                "organic_sentiment": organic_sentiment,
                "promo_sentiment": promo_sentiment,
                "sentiment_distribution": {
                    "positive": b.get("positive_count") or 0,
                    "negative": b.get("negative_count") or 0,
                    "neutral": b.get("neutral_count") or 0,
                },
                "spam_distribution": spam_dist,
                "original_terms": [
                    {"text": text, "count": count}
                    for text, count in sorted(
                        b["original_terms_counts"].items(),
                        key=lambda x: (len(x[0] or ""), x[1]),
                        reverse=True,
                    )[:20]
                ],
                "source_tasks": source_tasks,
                "post_ids_sample": b["post_ids_sample"],
                # Distributions
                "platform_distribution": dict(b["platform_dist"]),
                "organic_platform_distribution": dict(b["organic_platform_dist"]),
                "promo_platform_distribution": dict(b["promo_platform_dist"]),
                "keyword_distribution": dict(b["keyword_dist"]),
                # Aggregated attributes (Stage 1)
                "top_features": _finalize_attr("features"),
                "top_issues": _finalize_attr("issues"),
                "top_expectations": _finalize_attr("expectations"),
                "top_audience": _finalize_attr("audience"),
                "top_scenarios": _finalize_attr("scenarios"),
                "top_market_factors": _finalize_attr("market_factors"),
                "top_competitors": _finalize_attr("competitors"),
            }
        )

    project_entities.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_entities = project_entities[:max_items]

    # ==================== Finalize Topics ====================
    project_topics: list[dict[str, Any]] = []
    for b in topic_bucket.values():
        mentions = len(b["mentions_set"])
        heat = float(b["heat"])
        score = float(calculate_score(heat, mentions))
        avg_sentiment = (
            b["sentiment_sum"] / b["sentiment_weight"]
            if b["sentiment_weight"] > 0
            else 0.0
        )
        organic_sentiment_t = (
            round(b["organic_sent_sum"] / b["organic_sent_w"], 2)
            if (b.get("organic_sent_w") or 0) > 0
            else None
        )
        promo_sentiment_t = (
            round(b["promo_sent_sum"] / b["promo_sent_w"], 2)
            if (b.get("promo_sent_w") or 0) > 0
            else None
        )

        source_tasks = [
            {"task_id": tid, "mentions": len(pids)}
            for tid, pids in sorted(
                b["source_tasks"].items(), key=lambda x: len(x[1]), reverse=True
            )
        ]

        # Spam 4D 分布
        spam_dist_t = _compute_spam_dist_4d_by_key(
            b["post_source_keys"], b["comment_source_keys"], spam_map_by_key
        )

        project_topics.append(
            {
                "name": b["name"],
                "category": b["category"],
                "sentiment": round(avg_sentiment, 2),
                "organic_sentiment": organic_sentiment_t,
                "promo_sentiment": promo_sentiment_t,
                "positive_mentions": int(b.get("positive_mentions") or 0),
                "negative_mentions": int(b.get("negative_mentions") or 0),
                "heat": round(heat, 3),
                "organic_heat": round(float(b.get("organic_heat") or 0.0), 3),
                "promo_heat": round(float(b.get("promo_heat") or 0.0), 3),
                "mentions": mentions,
                "score": round(score, 3),
                "spam_distribution": spam_dist_t,
                "original_terms": [
                    {"text": text, "count": count}
                    for text, count in sorted(
                        b["original_terms_counts"].items(),
                        key=lambda x: (len(x[0] or ""), x[1]),
                        reverse=True,
                    )[:20]
                ],
                "source_tasks": source_tasks,
                "post_ids_sample": b["post_ids_sample"],
                # Distributions
                "platform_distribution": dict(b["platform_dist"]),
                "keyword_distribution": dict(b["keyword_dist"]),
            }
        )

    project_topics.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    project_topics = project_topics[:max_items]

    # ==================== Finalize Aspects ====================
    project_aspects = []
    for cat, data in aspect_bucket.items():
        avg_sent = (
            data["sentiment_sum"] / data["sentiment_weight"]
            if data["sentiment_weight"] > 0
            else 0.0
        )
        project_aspects.append(
            {
                "category": cat,
                "heat": round(data["heat"], 2),
                "sentiment": round(avg_sent, 2),
                "mention_count": data["mention_count"],
                "top_keywords": sorted(
                    data["top_terms"].keys(),
                    key=lambda k: data["top_terms"][k],
                    reverse=True,
                )[:5],
                "platform_distribution": dict(data["platforms"]),
                "keyword_distribution": dict(data["keywords"]),
            }
        )
    project_aspects.sort(key=lambda x: x["heat"], reverse=True)

    # ==================== Finalize Overview ====================
    global_avg_sentiment = (
        global_sentiment_sum / global_sentiment_count
        if global_sentiment_count > 0
        else 0.0
    )
    organic_avg_sentiment = (
        organic_sentiment_sum / organic_sentiment_count
        if organic_sentiment_count > 0
        else None
    )
    promo_avg_sentiment = (
        promo_sentiment_sum / promo_sentiment_count
        if promo_sentiment_count > 0
        else None
    )

    # 去重后各平台帖子量（unique post_key 口径，与 unique_posts 总量一致）
    unique_platform_volume: dict[str, int] = defaultdict(int)
    for _pk, _info in post_info_by_key.items():
        _plat = str(_info.get("platform") or "unknown")
        unique_platform_volume[_plat] += 1

    overview = {
        # 任务级总量（不去重，与 platform_volume / keyword_volume 口径一致）
        "total_volume": total_volume,
        # 项目级去重后帖子量（基于 platform+post_id_on_platform）
        "unique_posts": unique_posts,
        "total_heat": round(total_heat, 2),
        # NSR 口径（-2~+2），与实体/话题 sentiment（-1~+1）量纲不同
        "global_nsr": round(global_avg_sentiment, 2),
        "organic_nsr": round(organic_avg_sentiment, 2)
        if organic_avg_sentiment is not None
        else None,
        "promo_nsr": round(promo_avg_sentiment, 2)
        if promo_avg_sentiment is not None
        else None,
        # 任务级原始平台分布（未去重，与 total_volume 口径一致）
        "platform_volume": dict(platform_volume),
        # 去重后平台分布（与 unique_posts 口径一致）
        "unique_platform_volume": dict(unique_platform_volume),
        "keyword_volume": dict(keyword_volume),
    }

    # ===== 输出（最终方案结构）=====
    # 说明：不再输出旧版 overview/details/charts/insights 顶层字段；
    # 旧信息将被折叠进 foundation/layers，供 Step2/Step3/Step4 消费。
    return {
        "meta": {
            "project_id": project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "subject": subject,
            "competitors": competitors or [],
            "weights_used": weights_used,
            "scope": {
                "mode": "selected_tasks",
                "included_task_ids": included_task_ids,
                "platforms": list(platform_volume.keys()),
                "keywords": list(keyword_volume.keys()),
            },
            "task_diagnostics": task_diagnostics,
            "spam_config": {"threshold": spam_threshold},
        },
        "foundation": {
            "dedup_stats": dedup_stats,
            # Stage1 先写入候选池；Stage2 会覆盖为归一化后的 aligned_entities/topics
            "aligned_entities": project_entities,
            "aligned_topics": project_topics,
        },
        "layers": {
            "landscape": {
                "freshness": freshness,
                "overview": overview,
            },
            # 文档口径：Topic 层命名为 intent
            "intent": {
                "topic_aspects": project_aspects,
            },
            # Focus 由 Stage2/Stage3 基于 subject 条件触发填充
            "focus": None,
        },
        "reports": {
            "landscape_report": None,
            "topic_report": None,
            "focus_report": None,
        },
    }
