from __future__ import annotations

import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import (
    invoke_chain_with_stats_sync,
)
from src.social_media.analysis.celery_tasks.aggregation.utils import (
    calculate_score,
    are_similar,
)
from src.llm.chains.social.entity_normalization_chain import (
    format_entities_for_clustering,
)

from src.social_media.analysis.constants import (
    MAX_POST_IDS_SAMPLE,
    ORIGINAL_TERMS_MAX,
    ORIGINAL_TERM_MAX_LEN,
)
from .utils import fallback_alias_map, merge_attr_items

logger = logging.getLogger(__name__)


def _program_cluster_entities(
    entities: list[dict[str, Any]],
    threshold: float = 0.9,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """程序归一：按相似度预聚类，返回用于 LLM 的压缩列表与 raw->rep 映射。

    说明：这是 LLM 归一化的前置降噪步骤，使用简单的相似度阈值即可。
    即使有少量漏合并，LLM 也能通过语义理解来补救。
    """
    ents = sorted(
        [e for e in entities if isinstance(e, dict) and (e.get("name") or "").strip()],
        key=lambda x: float(x.get("score") or 0.0),
        reverse=True,
    )

    rep_list: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}

    for e in ents:
        name = (e.get("name") or "").strip()
        if not name:
            continue

        assigned = None
        for rep in rep_list:
            if are_similar(rep["name"], name, threshold=threshold):
                assigned = rep["name"]
                rep.setdefault("_members", []).append(name)
                # 把重要度累加，让 LLM 更关注这个 cluster
                try:
                    rep["score"] = float(rep.get("score") or 0.0) + float(
                        e.get("score") or 0.0
                    )
                except Exception:
                    pass
                break

        if assigned is None:
            rep_item = {
                "name": name,
                "type": e.get("type") or "其他",
                "score": float(e.get("score") or 0.0),
                "hint": e.get("hint") or "",
                "_members": [name],
            }
            rep_list.append(rep_item)
            assigned = name

        mapping[name] = assigned

    # 把 cluster 成员信息塞进 hint，帮助 LLM 在 original_names 中覆盖全量
    for rep in rep_list:
        members = [m for m in rep.get("_members", []) if isinstance(m, str)]
        extras = [m for m in members if m != rep["name"]]
        if extras:
            base = (rep.get("hint") or "").strip()
            suffix = f"同义候选: {', '.join(extras[:8])}"
            rep["hint"] = f"{base} | {suffix}".strip(" |")
        rep.pop("_members", None)

    return rep_list, mapping


def normalize_entity_aliases(
    *,
    top_entities: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    subject: str | None = None,
    competitors: list[str] | None = None,
    topn: int = 300,
) -> dict[str, Any]:
    """Stage2-B1：实体别名归一（先程序预聚类，再 LLM 两阶段归一；失败降级）。"""
    task_keywords = task_keywords or []
    entity_llm_used = False
    entity_token_stats: dict[str, Any] | None = None
    entity_mapping: dict[str, str] = {}
    tags_mapping: dict[str, Any] = {}
    entity_mapping_program: dict[str, str] = {}
    # LLM 失败原因（exception 类型 / 解析失败 / phase1 空 等），供上游写入 stage2 stats，
    # 让前端区分"LLM 成功无需合并" vs "LLM 失败兜底"，避免静默降级被误读为系统优化
    llm_failure_reason: str | None = None
    # parent 先验：来自任务级聚合（投票），用于 hint 注入与 LLM 缺失时回填
    raw_parent_by_name: dict[str, str] = {}
    raw_type_by_name: dict[str, str] = {}
    raw_mentions_by_name: dict[str, int] = {}
    # 统计信息
    input_count = 0
    program_clustered_count = 0
    input_names: list[str] = []

    try:
        ents_sorted = sorted(
            [
                e
                for e in top_entities
                if isinstance(e, dict) and (e.get("name") or "").strip()
            ],
            key=lambda x: float(x.get("score") or 0.0),
            reverse=True,
        )[:topn]

        ent_inputs = []
        for e in ents_sorted:
            name = (e.get("name") or "").strip()
            etype = str(e.get("type") or "")
            score = float(e.get("score") or 0.0)
            try:
                mentions = int(e.get("mentions") or 0)
            except Exception:
                mentions = 0
            parent = str(e.get("parent") or "").strip()
            if etype.strip().lower() == "brand" and not parent:
                # 任务级约定：品牌自身可用 Self（用于集团军聚合）
                parent = "Self"
            raw_parent_by_name[name] = parent
            raw_type_by_name[name] = etype or "其他"
            raw_mentions_by_name[name] = max(mentions, 1)
            p = (
                (e.get("platform_distribution") or {})
                if isinstance(e.get("platform_distribution"), dict)
                else {}
            )
            k = (
                (e.get("keyword_distribution") or {})
                if isinstance(e.get("keyword_distribution"), dict)
                else {}
            )
            p_hint = ",".join(
                [
                    kk
                    for kk, _ in sorted(p.items(), key=lambda x: x[1], reverse=True)[:2]
                ]
            )
            k_hint = ",".join(
                [
                    kk
                    for kk, _ in sorted(k.items(), key=lambda x: x[1], reverse=True)[:2]
                ]
            )
            hint = f"平台:{p_hint} 关键词:{k_hint}".strip()
            ent_inputs.append(
                {
                    "name": name,
                    "type": etype or "其他",
                    "score": score,
                    "hint": hint,
                }
            )
            input_names.append(name)
        input_count = len(ent_inputs)

        # 程序预聚类（减少 token + 给 LLM original_names 提示）
        ent_inputs_program, entity_mapping_program = _program_cluster_entities(
            ent_inputs
        )
        program_clustered_count = len(ent_inputs_program)

        # ===== parent 投票（程序聚类后的 cluster 级别），作为 hint 注入 LLM =====
        rep_parent_counts: dict[str, dict[str, int]] = {}
        if entity_mapping_program:
            for raw, rep in entity_mapping_program.items():
                parent = (raw_parent_by_name.get(raw) or "").strip()
                if not parent:
                    continue
                w = int(raw_mentions_by_name.get(raw, 1) or 1)
                rep_parent_counts.setdefault(rep, {})
                rep_parent_counts[rep][parent] = (
                    int(rep_parent_counts[rep].get(parent, 0)) + w
                )

        rep_parent_best: dict[str, str] = {}
        for rep, mp in rep_parent_counts.items():
            if not mp:
                continue
            rep_parent_best[rep] = max(mp.items(), key=lambda x: x[1])[0]

        for rep_item in ent_inputs_program:
            if not isinstance(rep_item, dict):
                continue
            rep_name = (rep_item.get("name") or "").strip()
            if not rep_name:
                continue
            parent_hint = rep_parent_best.get(rep_name)
            if parent_hint:
                base = (rep_item.get("hint") or "").strip()
                rep_item["hint"] = f"{base} parent候选:{parent_hint}".strip()

        formatted = format_entities_for_clustering(ent_inputs_program)
        if formatted.strip():
            # 项目级：使用专用 merge chain（支持 subject/competitors 仲裁）
            from src.llm.chains.social.monitor_entity_merge_chain import (
                merge_monitor_entities_with_review_sync,
            )

            # 使用两阶段归一化（Merge + Review）
            llm_result, stats = merge_monitor_entities_with_review_sync(
                entities_text=formatted,
                subject=(subject or "").strip(),
                competitors=[
                    str(x).strip() for x in (competitors or []) if str(x).strip()
                ],
                invoke_with_stats_fn=invoke_chain_with_stats_sync,
                enable_review=True,
                llm_type="chat",
            )

            entity_mapping = (llm_result or {}).get("entity_mapping") or {}
            tags_mapping = (llm_result or {}).get("tags_mapping") or {}
            # 提取链层报告的失败原因（解析失败 / phase 空 / phase2 兜底）
            llm_failure_reason = (llm_result or {}).get("failure_reason")

            # 去 Role 模式保护：subject 为空时强制 Context
            if not (subject or "").strip():
                for k, v in list(tags_mapping.items()):
                    if isinstance(v, dict):
                        v["role"] = "Context"
                        tags_mapping[k] = v

            if entity_mapping:
                entity_llm_used = True
                entity_token_stats = stats
    except Exception as e:
        logger.error(
            "[Slice Stage2] Entity alias normalization failed: %s", e, exc_info=True
        )
        # 顶层 exception 也记一下，让前端能看见
        llm_failure_reason = f"exception: {type(e).__name__}: {e}"

    if not entity_mapping:
        # 降级：优先用程序预聚类的映射
        if entity_mapping_program:
            entity_mapping = dict(entity_mapping_program)
        else:
            names = [
                str(e.get("name")).strip()
                for e in top_entities
                if isinstance(e, dict) and e.get("name")
            ]
            entity_mapping = fallback_alias_map(names)

    # 补全：确保程序聚类成员都有映射（避免 LLM 漏掉某些 original_names）
    if entity_mapping_program:
        for raw, rep in entity_mapping_program.items():
            if raw in entity_mapping:
                continue
            entity_mapping[raw] = entity_mapping.get(rep, rep)

    # ===== parent 投票（最终 canonical 级别），用于回填 tags_mapping.parent =====
    canon_parent_counts: dict[str, dict[str, int]] = {}
    for raw, canon in entity_mapping.items():
        rr = str(raw or "").strip()
        cc = str(canon or "").strip()
        if not rr or not cc:
            continue
        parent = (raw_parent_by_name.get(rr) or "").strip()
        etype = (raw_type_by_name.get(rr) or "").strip()
        if etype.lower() == "brand" and not parent:
            parent = "Self"
        if not parent:
            continue
        w = int(raw_mentions_by_name.get(rr, 1) or 1)
        canon_parent_counts.setdefault(cc, {})
        canon_parent_counts[cc][parent] = (
            int(canon_parent_counts[cc].get(parent, 0)) + w
        )

    for canon, mp in canon_parent_counts.items():
        if not mp:
            continue
        parent_guess = max(mp.items(), key=lambda x: x[1])[0]
        cur = tags_mapping.get(canon)
        if not isinstance(cur, dict):
            cur = {"role": "Context", "parent": ""}
        if not (cur.get("parent") or "").strip():
            cur["parent"] = parent_guess
        tags_mapping[canon] = cur

    # subject 为空时，确保所有输出 role=Context（包括回填条目）
    if not (subject or "").strip():
        for k, v in list(tags_mapping.items()):
            if isinstance(v, dict):
                v["role"] = "Context"
                tags_mapping[k] = v

    # ========== 输出归一化差异总结 ==========
    merged_groups: dict[str, list[str]] = {}
    for raw, canon in entity_mapping.items():
        if raw != canon:
            merged_groups.setdefault(canon, []).append(raw)

    final_unique = list(set(entity_mapping.values()))

    logger.info("=" * 60)
    logger.info("[项目级实体归一化] 统计总结:")
    logger.info("  - 原始输入: %s 个实体", input_count)
    logger.info("  - 程序归一后: %s 个实体", program_clustered_count)
    logger.info("  - LLM 归一后: %s 个实体", len(final_unique))
    logger.info("  - 被合并的实体组数: %s", len(merged_groups))
    logger.info("  - LLM 是否使用: %s", entity_llm_used)

    # 打印输入实体名称（前30）
    if input_names:
        logger.info("[项目级实体归一化] 输入实体名称（前30）:")
        logger.info("  %s", input_names[:30])

    # 打印归一化后的实体名称（前30）
    if final_unique:
        sorted_final = sorted(final_unique)[:30]
        logger.info("[项目级实体归一化] 归一化后实体名称（前30）:")
        logger.info("  %s", sorted_final)

    if merged_groups:
        logger.info("[项目级实体归一化] 合并详情（显示前 20 组）:")
        for i, (canon, members) in enumerate(
            sorted(merged_groups.items(), key=lambda x: len(x[1]), reverse=True)[:20]
        ):
            logger.info("  %s. [%s] ← %s", i + 1, canon, members)
    logger.info("=" * 60)

    return {
        "used": entity_llm_used,
        "token_stats": entity_token_stats,
        "entity_mapping": entity_mapping,
        "tags_mapping": tags_mapping,
        "program_mapping": entity_mapping_program,
        # 统计信息：原始数量、程序归一后送入 LLM 的数量
        "input_count": input_count,
        "program_clustered_count": program_clustered_count,
        # LLM 失败原因（None 表示成功或纯程序兜底无 LLM 调用）；
        # 上游写入 stage2.alias_normalization.entities.llm_failure_reason 供前端展示
        "llm_failure_reason": llm_failure_reason,
    }


def _merge_original_terms_to_counts(
    term_counts: dict[str, int], original_terms: list[dict[str, Any]] | None
) -> None:
    """合并 original_terms 到计数字典（用于实体归一化后的原话合并）。"""
    if not original_terms:
        return
    for t in original_terms:
        if not isinstance(t, dict):
            continue
        text = (t.get("text") or "").strip()
        if not text:
            continue
        # 工程防御：限制单条原话长度
        if len(text) > ORIGINAL_TERM_MAX_LEN:
            text = text[:ORIGINAL_TERM_MAX_LEN]
        try:
            count = int(t.get("count") or 0)
        except Exception:
            count = 0
        if count <= 0:
            count = 1
        term_counts[text] = term_counts.get(text, 0) + count


def build_entities_aligned(
    *,
    top_entities: list[dict[str, Any]],
    entity_mapping: dict[str, str],
    tags_mapping: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """根据 entity_mapping 合并 Stage1 top_entities，产出对齐后的实体列表。

    关键变更（对齐 PROJECT_SLICE_PIPELINE_FINAL.md）：
    - 合并 original_terms 列表并截断 Top 20（长度优先）。
    """
    tags_mapping = tags_mapping or {}
    max_post_ids_sample = MAX_POST_IDS_SAMPLE
    bucket: dict[str, dict[str, Any]] = {}
    for e in top_entities or []:
        if not isinstance(e, dict):
            continue
        raw_name = (e.get("name") or "").strip()
        if not raw_name:
            continue
        canon = (entity_mapping.get(raw_name) or raw_name).strip()
        b = bucket.get(canon)
        if not b:
            b = {
                "name": canon,
                "type": e.get("type"),
                "role": e.get("role"),
                "category": e.get("category"),
                "heat": 0.0,
                "organic_heat": 0.0,
                "promo_heat": 0.0,
                "mentions": 0,
                # 情感聚合字段（用于行业象限散点图）
                "sentiment_weighted_sum": 0.0,
                "sentiment_weight": 0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "platform_distribution": {},
                "organic_platform_distribution": {},
                "promo_platform_distribution": {},
                "keyword_distribution": {},
                "top_features": [],
                "top_issues": [],
                "top_expectations": [],
                "top_audience": [],
                "top_scenarios": [],
                "top_market_factors": [],
                "top_competitors": [],
                "original_names": [],
                "original_terms_counts": {},  # 原话合并
                "post_ids_sample": [],
                "_post_ids_sample_set": set(),
                "source_tasks": {},
                # Spam 4D 分布累加器
                "_spam_high_post": 0,
                "_spam_high_comment": 0,
                "_spam_low_post": 0,
                "_spam_low_comment": 0,
                "_spam_found": False,
                # 有机/推广情感累加器
                "organic_sent_weighted_sum": 0.0,
                "organic_sent_weight": 0.0,
                "promo_sent_weighted_sum": 0.0,
                "promo_sent_weight": 0.0,
            }
            bucket[canon] = b
        b["original_names"].append(raw_name)
        b["heat"] += float(e.get("heat") or 0.0)
        b["organic_heat"] += float(e.get("organic_heat") or 0.0)
        b["promo_heat"] += float(e.get("promo_heat") or 0.0)
        entity_mentions = int(e.get("mentions") or 0)
        b["mentions"] += entity_mentions
        # 情感累加（加权平均，按 mentions 加权）
        entity_sentiment = e.get("sentiment")
        if entity_sentiment is not None:
            try:
                sent_val = float(entity_sentiment)
                b["sentiment_weighted_sum"] += sent_val * entity_mentions
                b["sentiment_weight"] += entity_mentions
            except Exception:
                pass
        # 情感分布累加
        sent_dist = e.get("sentiment_distribution")
        if isinstance(sent_dist, dict):
            try:
                b["positive_count"] += int(sent_dist.get("positive") or 0)
                b["negative_count"] += int(sent_dist.get("negative") or 0)
                b["neutral_count"] += int(sent_dist.get("neutral") or 0)
            except Exception:
                pass
        for k, v in (e.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = (
                    int(b["platform_distribution"].get(k, 0)) + vv
                )
        for k, v in (e.get("organic_platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["organic_platform_distribution"][k] = (
                    int(b["organic_platform_distribution"].get(k, 0)) + vv
                )
        for k, v in (e.get("promo_platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["promo_platform_distribution"][k] = (
                    int(b["promo_platform_distribution"].get(k, 0)) + vv
                )
        for k, v in (e.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = (
                    int(b["keyword_distribution"].get(k, 0)) + vv
                )
        # 来源任务聚合（用于可追溯）
        for st in e.get("source_tasks") or []:
            if not isinstance(st, dict):
                continue
            try:
                tid = int(st.get("task_id") or 0)
                cnt = int(st.get("mentions") or 0)
            except Exception:
                continue
            if tid <= 0 or cnt <= 0:
                continue
            b["source_tasks"][tid] = int(b["source_tasks"].get(tid, 0)) + cnt
        # Spam 分布累加
        sd = e.get("spam_distribution")
        if isinstance(sd, dict):
            hs = sd.get("high_spam")
            ls = sd.get("low_spam")
            if isinstance(hs, dict) or isinstance(ls, dict):
                b["_spam_found"] = True
            if isinstance(hs, dict):
                b["_spam_high_post"] += int(hs.get("post") or 0)
                b["_spam_high_comment"] += int(hs.get("comment") or 0)
            if isinstance(ls, dict):
                b["_spam_low_post"] += int(ls.get("post") or 0)
                b["_spam_low_comment"] += int(ls.get("comment") or 0)
            # 有机/推广情感累加（按 spam_distribution 总量加权）
            low_total = int((ls or {}).get("total") or 0) if isinstance(ls, dict) else 0
            high_total = int((hs or {}).get("total") or 0) if isinstance(hs, dict) else 0
            organic_sent = e.get("organic_sentiment")
            promo_sent = e.get("promo_sentiment")
            if organic_sent is not None and low_total > 0:
                try:
                    b["organic_sent_weighted_sum"] += float(organic_sent) * low_total
                    b["organic_sent_weight"] += low_total
                except Exception:
                    pass
            if promo_sent is not None and high_total > 0:
                try:
                    b["promo_sent_weighted_sum"] += float(promo_sent) * high_total
                    b["promo_sent_weight"] += high_total
                except Exception:
                    pass
        # 原文样本合并（去重 + 限制数量）
        for ref in e.get("post_ids_sample") or []:
            if len(b["post_ids_sample"]) >= max_post_ids_sample:
                break
            if not isinstance(ref, dict):
                continue
            try:
                tid = int(ref.get("task_id") or 0)
                pid = int(ref.get("post_id") or 0)
            except Exception:
                continue
            if tid <= 0 or pid <= 0:
                continue
            key = f"{tid}:{pid}"
            if key in b["_post_ids_sample_set"]:
                continue
            b["_post_ids_sample_set"].add(key)
            b["post_ids_sample"].append({"task_id": tid, "post_id": pid})
        # 属性合并（Set Union）
        b["top_features"].extend(e.get("top_features") or [])
        b["top_issues"].extend(e.get("top_issues") or [])
        b["top_expectations"].extend(e.get("top_expectations") or [])
        b["top_audience"].extend(e.get("top_audience") or [])
        b["top_scenarios"].extend(e.get("top_scenarios") or [])
        b["top_market_factors"].extend(e.get("top_market_factors") or [])
        b["top_competitors"].extend(e.get("top_competitors") or [])
        # 原话合并
        _merge_original_terms_to_counts(
            b["original_terms_counts"], e.get("original_terms")
        )

    aligned: list[dict[str, Any]] = []
    for _, b in bucket.items():
        mentions = int(b["mentions"] or 0)
        heat = float(b["heat"] or 0.0)
        score = float(calculate_score(heat, mentions)) if mentions > 0 else 0.0
        # 计算加权平均情感值
        sentiment_weight = b.get("sentiment_weight") or 0
        if sentiment_weight > 0:
            sentiment = round(b["sentiment_weighted_sum"] / sentiment_weight, 2)
        else:
            sentiment = 0.0
        # 构建 original_terms 列表（长度优先排序，截断 Top ORIGINAL_TERMS_MAX）
        original_terms = [
            {"text": text, "count": count}
            for text, count in sorted(
                (b.get("original_terms_counts") or {}).items(),
                key=lambda x: (len(x[0] or ""), x[1]),  # 长度优先，次按 count
                reverse=True,
            )[:ORIGINAL_TERMS_MAX]
        ]
        # Spam 4D 分布
        spam_distribution = None
        if b.get("_spam_found"):
            hp = b["_spam_high_post"]
            hc = b["_spam_high_comment"]
            lp = b["_spam_low_post"]
            lc = b["_spam_low_comment"]
            spam_distribution = {
                "high_spam": {"total": hp + hc, "post": hp, "comment": hc},
                "low_spam": {"total": lp + lc, "post": lp, "comment": lc},
            }
        # 有机/推广情感
        organic_sentiment = None
        if (b.get("organic_sent_weight") or 0) > 0:
            organic_sentiment = round(b["organic_sent_weighted_sum"] / b["organic_sent_weight"], 2)
        promo_sentiment = None
        if (b.get("promo_sent_weight") or 0) > 0:
            promo_sentiment = round(b["promo_sent_weighted_sum"] / b["promo_sent_weight"], 2)

        aligned.append(
            {
                "name": b["name"],
                "type": b.get("type"),
                "category": b.get("category"),
                "role": (tags_mapping.get(b["name"], {}) or {}).get("role")
                or b.get("role"),
                "parent": (tags_mapping.get(b["name"], {}) or {}).get("parent") or "",
                "heat": round(heat, 3),
                "organic_heat": round(float(b.get("organic_heat") or 0.0), 3),
                "promo_heat": round(float(b.get("promo_heat") or 0.0), 3),
                "mentions": mentions,
                "score": round(score, 3),
                # 情感字段（用于行业象限散点图）
                "sentiment": sentiment,
                "organic_sentiment": organic_sentiment,
                "promo_sentiment": promo_sentiment,
                "sentiment_distribution": {
                    "positive": b.get("positive_count") or 0,
                    "negative": b.get("negative_count") or 0,
                    "neutral": b.get("neutral_count") or 0,
                },
                "spam_distribution": spam_distribution,
                "platform_distribution": b["platform_distribution"],
                "organic_platform_distribution": b.get("organic_platform_distribution") or {},
                "promo_platform_distribution": b.get("promo_platform_distribution") or {},
                "keyword_distribution": b["keyword_distribution"],
                "source_tasks": [
                    {"task_id": tid, "mentions": cnt}
                    for tid, cnt in sorted(
                        (b.get("source_tasks") or {}).items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                ],
                "post_ids_sample": b.get("post_ids_sample") or [],
                "top_features": merge_attr_items(b.get("top_features")),
                "top_issues": merge_attr_items(b.get("top_issues")),
                "top_expectations": merge_attr_items(b.get("top_expectations")),
                "top_audience": merge_attr_items(b.get("top_audience")),
                "top_scenarios": merge_attr_items(b.get("top_scenarios")),
                "top_market_factors": merge_attr_items(b.get("top_market_factors")),
                "top_competitors": merge_attr_items(b.get("top_competitors")),
                "original_names": sorted(set(b["original_names"])),
                "original_terms": original_terms,  # 用户原话
            }
        )
    aligned.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return aligned
