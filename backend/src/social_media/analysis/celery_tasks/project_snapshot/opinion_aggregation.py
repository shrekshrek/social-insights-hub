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
    items = sorted(
        [(t, int(c or 0)) for t, c in (term_counts or {}).items() if t],
        key=lambda x: x[1],
        reverse=True,
    )
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


def _format_opinions_for_llm(
    rep_counts: dict[str, int], rep_members: dict[str, list[str]], top_k: int = 80
) -> str:
    lines: list[str] = []
    for rep, cnt in sorted(rep_counts.items(), key=lambda x: x[1], reverse=True)[
        :top_k
    ]:
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
                resp, stats = invoke_chain_with_stats_sync(
                    chain, {"categories": formatted}, "chat"
                )
                text = resp.content if hasattr(resp, "content") else str(resp)
                category_map = parse_category_normalization_response(text) or {}
                if category_map:
                    llm_used = True
                    token_stats = stats
    except Exception as e:
        logger.error(
            f"[Snapshot Opinion] Category alignment failed: {e}", exc_info=True
        )

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
        topics_for_norm.append(
            {
                **t,
                "category_aligned": map_category(
                    (t.get("category") or "").strip() or "其他"
                ),
            }
        )

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
    cat_alignment_result = _align_categories_for_topics(top_topics)
    topics_for_norm = cat_alignment_result.get("topics_for_norm") or []

    topic_llm_used = False
    token_stats_list: list[dict[str, Any]] = []
    topic_mapping_by_category: dict[str, dict[str, str]] = {}
    program_mapping_by_category: dict[str, dict[str, str]] = {}
    # 统计信息
    input_count = len([t for t in top_topics if isinstance(t, dict)])
    total_program_clustered = 0

    grouped: dict[str, dict[str, int]] = {}
    for t in topics_for_norm or []:
        if not isinstance(t, dict):
            continue
        cat_name = (t.get("category_aligned") or "其他").strip() or "其他"
        nm = (t.get("name") or "").strip()
        if not nm:
            continue
        try:
            w = int(t.get("mentions") or 0)
        except Exception:
            w = 0
        if w <= 0:
            w = 1
        grouped.setdefault(cat_name, {})
        grouped[cat_name][nm] = grouped[cat_name].get(nm, 0) + w

    for cat_name, mp in grouped.items():
        # 候选池来自快照 top_topics（建议 200），这里按类目控制送入归一化的上限
        top_terms = dict(sorted(mp.items(), key=lambda x: x[1], reverse=True)[:100])
        # 程序预聚类（降噪/降 token）
        rep_counts, raw_to_rep, rep_members = _program_cluster_terms(top_terms)
        program_mapping_by_category[cat_name] = raw_to_rep
        total_program_clustered += len(rep_counts)
        try:
            chain = create_opinion_normalization_chain()
            formatted = _format_opinions_for_llm(rep_counts, rep_members, top_k=100)
            resp, stats = invoke_chain_with_stats_sync(
                chain, {"category": cat_name, "opinions": formatted}, "chat"
            )
            text = resp.content if hasattr(resp, "content") else str(resp)
            clusters = parse_opinion_normalization_response(text)
            if clusters:
                m = build_term_to_cluster(clusters)
                # 补全：把程序聚类成员也映射到 canonical（避免 LLM 漏掉）
                full_map: dict[str, str] = {}
                for raw, rep in raw_to_rep.items():
                    full_map[raw] = m.get(raw) or m.get(rep) or rep
                topic_mapping_by_category[cat_name] = full_map
                topic_llm_used = True
                if stats:
                    token_stats_list.append(stats)
                continue
        except Exception as e:
            logger.error(
                f"[Snapshot Stage2] Topic alias normalization failed: {e}",
                exc_info=True,
            )

        # fallback：直接使用程序预聚类映射（或最简单映射）
        if raw_to_rep:
            topic_mapping_by_category[cat_name] = raw_to_rep
        else:
            topic_mapping_by_category[cat_name] = fallback_alias_map(
                list(top_terms.keys())
            )

    # ========== 输出归一化差异总结 ==========
    total_merged_groups = 0
    total_llm_output = 0

    # 输入观点名称列表
    input_names = [
        t.get("name") for t in top_topics if isinstance(t, dict) and t.get("name")
    ][:50]

    logger.info("=" * 60)
    logger.info("[项目级观点归一化] 统计总结:")
    logger.info(f"  - 原始输入: {input_count} 个观点")
    logger.info(
        f"  - 程序归一后: {total_program_clustered} 个观点（跨 {len(grouped)} 个类目）"
    )

    # 打印输入观点名称（前30）
    logger.info("[项目级观点归一化] 输入观点名称（前30）:")
    logger.info(f"  {input_names[:30]}")

    # 类目对齐信息
    cat_map = cat_alignment_result.get("category_map") or {}
    if cat_map:
        logger.info(f"  - 类目对齐: {len(cat_map)} 个类目被映射")
        for old_cat, new_cat in list(cat_map.items())[:10]:
            if old_cat != new_cat:
                logger.info(f"    [{old_cat}] → [{new_cat}]")

    # 按类目统计合并详情
    logger.info("[项目级观点归一化] 各类目合并详情:")
    for cat_name, mapping in topic_mapping_by_category.items():
        merged_in_cat: dict[str, list[str]] = {}
        for raw, canon in mapping.items():
            if raw != canon:
                merged_in_cat.setdefault(canon, []).append(raw)
        unique_canons = len(set(mapping.values()))
        total_llm_output += unique_canons
        total_merged_groups += len(merged_in_cat)

        if merged_in_cat:
            logger.info(
                f"  [{cat_name}] 输入:{len(mapping)} → 输出:{unique_canons}, 合并组:{len(merged_in_cat)}"
            )
            for canon, members in sorted(
                merged_in_cat.items(), key=lambda x: len(x[1]), reverse=True
            )[:5]:
                logger.info(f"    [{canon}] ← {members[:8]}")

    logger.info(f"  - LLM 归一后总计: {total_llm_output} 个观点")
    logger.info(f"  - 被合并的观点组总数: {total_merged_groups}")
    logger.info(f"  - LLM 是否使用: {topic_llm_used}")
    logger.info("=" * 60)

    return {
        "used": topic_llm_used,
        "category_alignment": {
            "used": bool(cat_alignment_result.get("used")),
            "token_stats": cat_alignment_result.get("token_stats"),
            "category_map": cat_alignment_result.get("category_map") or {},
        },
        "topics_for_norm": topics_for_norm,
        "token_stats_list": token_stats_list,
        "topic_mapping_by_category": topic_mapping_by_category,
        "program_mapping_by_category": program_mapping_by_category,
        # 统计信息：原始数量、程序归一后送入 LLM 的总数量
        "input_count": input_count,
        "program_clustered_count": total_program_clustered,
    }


def build_topics_aligned(
    *,
    topics_for_norm: list[dict[str, Any]],
    topic_mapping_by_category: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """根据 category_aligned + mapping 合并 topics_for_norm，产出对齐后的观点列表。"""
    max_post_ids_sample = 50

    def _cap_text(s: str) -> str:
        s = (s or "").strip()
        if len(s) > 100:
            s = s[:100]
        return s

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
                "organic_heat": 0.0,
                "promo_heat": 0.0,
                "mentions": 0,
                "sentiment_sum": 0.0,
                "sentiment_weight": 0.0,
                "platform_distribution": {},
                "keyword_distribution": {},
                "original_terms_counts": {},
                "post_ids_sample": [],
                "_post_ids_sample_set": set(),
                "source_tasks": {},
                # Spam 4D 分布累加器
                "_spam_high_post": 0,
                "_spam_high_comment": 0,
                "_spam_low_post": 0,
                "_spam_low_comment": 0,
                "_spam_found": False,
                # 正/负极性计数（用于争议性检测）
                "positive_mentions": 0,
                "negative_mentions": 0,
                # 有机/推广情感
                "organic_sent_sum": 0.0,
                "organic_sent_w": 0.0,
                "promo_sent_sum": 0.0,
                "promo_sent_w": 0.0,
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
        b["organic_heat"] += float(t.get("organic_heat") or 0.0)
        b["promo_heat"] += float(t.get("promo_heat") or 0.0)
        try:
            s = float(t.get("sentiment") or 0.0)
        except Exception:
            s = 0.0
        b["sentiment_sum"] += s * float(m)
        b["sentiment_weight"] += float(m)
        b["positive_mentions"] += int(t.get("positive_mentions") or 0)
        b["negative_mentions"] += int(t.get("negative_mentions") or 0)
        org_sent = t.get("organic_sentiment")
        if org_sent is not None and m > 0:
            try:
                b["organic_sent_sum"] += float(org_sent) * float(m)
                b["organic_sent_w"] += float(m)
            except Exception:
                pass
        promo_sent = t.get("promo_sentiment")
        if promo_sent is not None and m > 0:
            try:
                b["promo_sent_sum"] += float(promo_sent) * float(m)
                b["promo_sent_w"] += float(m)
            except Exception:
                pass

        for k, v in (t.get("platform_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["platform_distribution"][k] = (
                    int(b["platform_distribution"].get(k, 0)) + vv
                )
        for k, v in (t.get("keyword_distribution") or {}).items():
            try:
                vv = int(v or 0)
            except Exception:
                vv = 0
            if vv:
                b["keyword_distribution"][k] = (
                    int(b["keyword_distribution"].get(k, 0)) + vv
                )
        # 来源任务聚合（用于可追溯）
        for st in t.get("source_tasks") or []:
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
        sd = t.get("spam_distribution")
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
        # 帖子样本合并（去重 + 限制数量）
        for ref in t.get("post_ids_sample") or []:
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
            key_id = f"{tid}:{pid}"
            if key_id in b["_post_ids_sample_set"]:
                continue
            b["_post_ids_sample_set"].add(key_id)
            b["post_ids_sample"].append({"task_id": tid, "post_id": pid})

        # 合并原话：优先使用任务级聚合下发的 original_terms；没有则回退用观点名占位
        ots = t.get("original_terms")
        if isinstance(ots, list) and ots:
            for it in ots:
                if not isinstance(it, dict):
                    continue
                txt = _cap_text(str(it.get("text") or ""))
                if not txt:
                    continue
                try:
                    c = int(it.get("count") or 0)
                except Exception:
                    c = 0
                if c <= 0:
                    c = 1
                b["original_terms_counts"][txt] = (
                    int(b["original_terms_counts"].get(txt, 0)) + c
                )
        else:
            txt = _cap_text(raw_name)
            if txt:
                b["original_terms_counts"][txt] = (
                    int(b["original_terms_counts"].get(txt, 0)) + 1
                )

    aligned: list[dict[str, Any]] = []
    for _, b in bucket.items():
        avg_sent = (
            (b["sentiment_sum"] / b["sentiment_weight"])
            if b["sentiment_weight"] > 0
            else 0.0
        )
        score = float(calculate_score(float(b["heat"]), int(b["mentions"])))
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

        aligned.append(
            {
                "name": b["name"],
                "category": b["category"],
                "heat": round(float(b["heat"]), 3),
                "organic_heat": round(float(b["organic_heat"]), 3),
                "promo_heat": round(float(b["promo_heat"]), 3),
                "mentions": int(b["mentions"]),
                "sentiment": round(float(avg_sent), 2),
                "organic_sentiment": (
                    round(b["organic_sent_sum"] / b["organic_sent_w"], 2)
                    if (b.get("organic_sent_w") or 0) > 0
                    else None
                ),
                "promo_sentiment": (
                    round(b["promo_sent_sum"] / b["promo_sent_w"], 2)
                    if (b.get("promo_sent_w") or 0) > 0
                    else None
                ),
                "positive_mentions": int(b.get("positive_mentions") or 0),
                "negative_mentions": int(b.get("negative_mentions") or 0),
                "score": round(float(score), 3),
                "spam_distribution": spam_distribution,
                "platform_distribution": b["platform_distribution"],
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
                "original_terms": [
                    {"text": text, "count": count}
                    for text, count in sorted(
                        (b.get("original_terms_counts") or {}).items(),
                        key=lambda x: (len(x[0] or ""), x[1]),
                        reverse=True,
                    )[:20]
                ],
            }
        )
    aligned.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return aligned
