from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _norm_role(role: Any) -> str:
    """规范化 role 字段到 Target/Competitor/Context。"""
    if role is None:
        return "Context"
    r = str(role).strip().lower()
    if r in {"target", "t"}:
        return "Target"
    if r in {"competitor", "rival", "comp"}:
        return "Competitor"
    # 任务级旧口径：other/unknown
    return "Context"


def build_snapshot_layers(
    *,
    meta: dict[str, Any],
    overview: dict[str, Any],
    freshness: dict[str, Any] | None,
    entities_aligned: list[dict[str, Any]],
    topics_aligned: list[dict[str, Any]],
    drivers: dict[str, Any] | None,
) -> dict[str, Any]:
    """Step3：分层指标计算（Landscape/Topic/Focus）。

    说明：
    - 输出结构与 PROJECT_SNAPSHOT_PIPELINE_FINAL.md 对齐，但保持 KISS：先覆盖核心指标。
    - Focus 仅在 meta.subject 存在时返回，否则为 None。
    """
    freshness = freshness or {}
    subject = (meta or {}).get("subject")
    subject = str(subject).strip() if subject is not None else ""

    # ===== Landscape layer =====
    total_heat = 0.0
    total_organic_heat = 0.0
    total_promo_heat = 0.0
    for e in entities_aligned or []:
        try:
            total_heat += float(e.get("heat") or 0.0)
        except Exception:
            continue
        try:
            total_organic_heat += float(e.get("organic_heat") or 0.0)
        except Exception:
            pass
        try:
            total_promo_heat += float(e.get("promo_heat") or 0.0)
        except Exception:
            pass

    sov_ranking: list[dict[str, Any]] = []
    for e in entities_aligned[:100]:
        if not isinstance(e, dict):
            continue
        try:
            heat = float(e.get("heat") or 0.0)
        except Exception:
            heat = 0.0
        mentions = int(e.get("mentions") or 0)
        name = e.get("name") or ""
        parent = (e.get("parent") or "") if isinstance(e.get("parent"), str) else ""
        role = _norm_role(e.get("role"))
        post_ids_sample = e.get("post_ids_sample") or []
        source_tasks = e.get("source_tasks") or []
        # 情感字段（用于行业象限）
        try:
            sentiment = float(e.get("sentiment") or 0.0)
        except Exception:
            sentiment = 0.0
        sov_ranking.append(
            {
                "name": name,
                "parent": parent,
                "role": role,
                "heat": round(heat, 3),
                "organic_heat": e.get("organic_heat"),
                "promo_heat": e.get("promo_heat"),
                "mentions": mentions,
                "share": round((heat / total_heat), 6) if total_heat > 0 else 0.0,
                "sentiment": round(sentiment, 2),
                "organic_sentiment": e.get("organic_sentiment"),
                "promo_sentiment": e.get("promo_sentiment"),
                "platform_distribution": e.get("platform_distribution") or {},
                "post_ids_sample": post_ids_sample,
                "source_tasks": source_tasks,
                "spam_distribution": e.get("spam_distribution"),
            }
        )

    # Group/Parent aggregation（集团军声量）
    group_bucket: dict[str, dict[str, Any]] = {}
    for e in entities_aligned or []:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name") or "").strip()
        if not nm:
            continue
        parent = str(e.get("parent") or "").strip()
        # 约定：parent="" 或 "Self" 时用自身作为 parent
        group = nm if not parent or parent.lower() == "self" else parent
        b = group_bucket.setdefault(
            group,
            {
                "name": group,
                "heat": 0.0,
                "organic_heat": 0.0,
                "promo_heat": 0.0,
                "mentions": 0,
                "_spam_high_post": 0,
                "_spam_high_comment": 0,
                "_spam_low_post": 0,
                "_spam_low_comment": 0,
                "_has_spam": False,
                # 有机/推广情感累加
                "organic_sent_weighted_sum": 0.0,
                "organic_sent_weight": 0.0,
                "promo_sent_weighted_sum": 0.0,
                "promo_sent_weight": 0.0,
            },
        )
        try:
            b["heat"] += float(e.get("heat") or 0.0)
        except Exception:
            pass
        try:
            b["organic_heat"] += float(e.get("organic_heat") or 0.0)
        except Exception:
            pass
        try:
            b["promo_heat"] += float(e.get("promo_heat") or 0.0)
        except Exception:
            pass
        try:
            b["mentions"] += int(e.get("mentions") or 0)
        except Exception:
            pass
        # Spam 分布累加
        sd = e.get("spam_distribution")
        if isinstance(sd, dict):
            hs = sd.get("high_spam")
            ls = sd.get("low_spam")
            if isinstance(hs, dict) and isinstance(ls, dict):
                b["_spam_high_post"] += int(hs.get("post") or 0)
                b["_spam_high_comment"] += int(hs.get("comment") or 0)
                b["_spam_low_post"] += int(ls.get("post") or 0)
                b["_spam_low_comment"] += int(ls.get("comment") or 0)
                b["_has_spam"] = True
                # 有机/推广情感加权累加
                low_total = int(ls.get("total") or 0)
                high_total = int(hs.get("total") or 0)
                organic_sent = e.get("organic_sentiment")
                promo_sent = e.get("promo_sentiment")
                if organic_sent is not None and low_total > 0:
                    try:
                        b["organic_sent_weighted_sum"] += (
                            float(organic_sent) * low_total
                        )
                        b["organic_sent_weight"] += low_total
                    except Exception:
                        pass
                if promo_sent is not None and high_total > 0:
                    try:
                        b["promo_sent_weighted_sum"] += float(promo_sent) * high_total
                        b["promo_sent_weight"] += high_total
                    except Exception:
                        pass
    group_share_items = []
    for k, v in group_bucket.items():
        item: dict[str, Any] = {
            "name": k,
            "heat": round(float(v.get("heat") or 0.0), 3),
            "organic_heat": round(float(v.get("organic_heat") or 0.0), 3),
            "promo_heat": round(float(v.get("promo_heat") or 0.0), 3),
            "mentions": int(v.get("mentions") or 0),
        }
        # 构建 spam_distribution
        if v.get("_has_spam"):
            hp = int(v.get("_spam_high_post") or 0)
            hc = int(v.get("_spam_high_comment") or 0)
            lp = int(v.get("_spam_low_post") or 0)
            lc = int(v.get("_spam_low_comment") or 0)
            item["spam_distribution"] = {
                "high_spam": {"total": hp + hc, "post": hp, "comment": hc},
                "low_spam": {"total": lp + lc, "post": lp, "comment": lc},
            }
            # 有机/推广情感
            item["organic_sentiment"] = (
                round(v["organic_sent_weighted_sum"] / v["organic_sent_weight"], 2)
                if (v.get("organic_sent_weight") or 0) > 0
                else None
            )
            item["promo_sentiment"] = (
                round(v["promo_sent_weighted_sum"] / v["promo_sent_weight"], 2)
                if (v.get("promo_sent_weight") or 0) > 0
                else None
            )
        else:
            item["spam_distribution"] = None
        group_share_items.append(item)

    group_share = sorted(
        group_share_items,
        key=lambda x: x.get("heat", 0.0),
        reverse=True,
    )[:30]

    overview_safe = overview if isinstance(overview, dict) else {}
    # 兜底：如果 Stage1 overview 在历史版本中被覆盖/裁剪，可用 meta.task_diagnostics 重建关键字段
    # （保证前端“概览”的 platform_volume/keyword_volume/global_sentiment 不丢）
    if isinstance(meta, dict):
        diag = meta.get("task_diagnostics")
    else:
        diag = None
    if isinstance(diag, list):
        need_platform = not isinstance(overview_safe.get("platform_volume"), dict)
        need_keyword = not isinstance(overview_safe.get("keyword_volume"), dict)
        need_sent = not isinstance(overview_safe.get("global_nsr"), (int, float))
        need_total = not isinstance(overview_safe.get("total_volume"), (int, float))

        if need_platform or need_keyword or need_sent or need_total:
            plat = defaultdict(int)
            kw = defaultdict(int)
            sent_sum = 0.0
            sent_w = 0
            total = 0
            for r in diag:
                if not isinstance(r, dict):
                    continue
                p = str(r.get("platform") or "unknown")
                k = str(r.get("keyword") or "unknown")
                try:
                    c = int(r.get("data_volume_total") or 0)
                except Exception:
                    c = 0
                if c < 0:
                    c = 0
                total += c
                plat[p] += c
                kw[k] += c
                try:
                    nsr = float(r.get("nsr") or 0.0)
                except Exception:
                    nsr = 0.0
                sent_sum += nsr * float(c)
                sent_w += c

            if need_total:
                overview_safe["total_volume"] = total
            if need_platform:
                overview_safe["platform_volume"] = dict(plat)
            if need_keyword:
                overview_safe["keyword_volume"] = dict(kw)
            if need_sent:
                overview_safe["global_nsr"] = (
                    round((sent_sum / sent_w), 2) if sent_w > 0 else 0.0
                )

    # 全局有机/推广热度总量（用于前端计算全局口径的有机/推广 SOV 份额）
    overview_safe["total_organic_heat"] = round(total_organic_heat, 3)
    overview_safe["total_promo_heat"] = round(total_promo_heat, 3)

    # --- 平台阵地 DNA：Top N 品牌在各平台的声量占比分布 ---
    platform_dna: list[dict[str, Any]] = []
    # 先收集所有平台
    all_platforms: set[str] = set()
    for item in sov_ranking[:20]:
        if not isinstance(item, dict):
            continue
        p_dist = item.get("platform_distribution") or {}
        if isinstance(p_dist, dict):
            all_platforms.update(p_dist.keys())
    all_platforms_sorted = sorted(all_platforms)

    for item in sov_ranking[:20]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        if not name:
            continue
        p_dist = item.get("platform_distribution") or {}
        org_dist = item.get("organic_platform_distribution") or {}
        promo_dist = item.get("promo_platform_distribution") or {}
        total_mentions = sum(int(v or 0) for v in p_dist.values()) if p_dist else 0
        total_organic = sum(int(v or 0) for v in org_dist.values()) if org_dist else 0
        total_promo = sum(int(v or 0) for v in promo_dist.values()) if promo_dist else 0
        # 构建各平台占比（全量 / 有机 / 推广）
        platform_shares: dict[str, float] = {}
        organic_platform_shares: dict[str, float] = {}
        promo_platform_shares: dict[str, float] = {}
        for p in all_platforms_sorted:
            cnt = int(p_dist.get(p) or 0)
            org_cnt = int(org_dist.get(p) or 0)
            promo_cnt = int(promo_dist.get(p) or 0)
            platform_shares[p] = (
                round(cnt / total_mentions, 4) if total_mentions > 0 else 0.0
            )
            organic_platform_shares[p] = (
                round(org_cnt / total_organic, 4) if total_organic > 0 else 0.0
            )
            promo_platform_shares[p] = (
                round(promo_cnt / total_promo, 4) if total_promo > 0 else 0.0
            )
        platform_dna.append(
            {
                "name": name,
                "role": item.get("role") or "Context",
                "total_mentions": total_mentions,
                "total_organic_mentions": total_organic,
                "total_promo_mentions": total_promo,
                "platform_shares": platform_shares,
                "organic_platform_shares": organic_platform_shares,
                "promo_platform_shares": promo_platform_shares,
            }
        )

    landscape = {
        "sov_ranking": sov_ranking,
        "group_share": group_share,
        "platform_dna": platform_dna,
        "freshness": freshness,
        # 透传 Stage1 overview（包含 platform_volume / keyword_volume / global_sentiment 等）
        "overview": overview_safe,
    }

    # ===== Topic layer =====
    pains: list[dict[str, Any]] = []
    gains: list[dict[str, Any]] = []
    controversies: list[dict[str, Any]] = []

    # 1) topic_radar：按 sentiment 分桶（可解释）
    for t in topics_aligned[:160]:
        if not isinstance(t, dict):
            continue
        try:
            sent = float(t.get("sentiment") or 0.0)
        except Exception:
            sent = 0.0
        pos_m = int(t.get("positive_mentions") or 0)
        neg_m = int(t.get("negative_mentions") or 0)
        item = {
            "name": t.get("name") or "",
            "category": t.get("category") or "其他",
            "heat": float(t.get("heat") or 0.0),
            "organic_heat": t.get("organic_heat"),
            "promo_heat": t.get("promo_heat"),
            "mentions": int(t.get("mentions") or 0),
            "sentiment": round(sent, 2),
            "organic_sentiment": t.get("organic_sentiment"),
            "promo_sentiment": t.get("promo_sentiment"),
            "positive_mentions": pos_m,
            "negative_mentions": neg_m,
            "spam_distribution": t.get("spam_distribution"),
            "platform_distribution": t.get("platform_distribution") or {},
            "keyword_distribution": t.get("keyword_distribution") or {},
            "original_terms": t.get("original_terms") or [],
            "post_ids_sample": t.get("post_ids_sample") or [],
            "source_tasks": t.get("source_tasks") or [],
        }
        # 分桶：负向主导→pains，正向主导→gains，真正有争议→controversies
        # 争议性条件：极性总数≥6 且少数派≥30%（双向声音都显著）
        polar_total = pos_m + neg_m
        is_controversial = polar_total >= 6 and min(pos_m, neg_m) / polar_total >= 0.3
        if sent <= -0.2:
            pains.append(item)
        elif sent >= 0.2:
            gains.append(item)
        elif is_controversial:
            controversies.append(item)
        # 情感中性且极性不够的话题不列入 radar（已被 topic_aspects 覆盖）

    pains.sort(key=lambda x: x.get("heat", 0.0), reverse=True)
    gains.sort(key=lambda x: x.get("heat", 0.0), reverse=True)
    controversies.sort(key=lambda x: x.get("heat", 0.0), reverse=True)

    # 2) topic_aspects：按 category 聚合（用于前端卡片/概览）
    asp2: dict[str, dict[str, Any]] = {}
    for t in topics_aligned or []:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category") or "其他").strip() or "其他"
        b = asp2.get(cat)
        if not b:
            b = {
                "category": cat,
                "heat": 0.0,
                "organic_heat": 0.0,
                "promo_heat": 0.0,
                "sentiment_sum": 0.0,
                "sentiment_weight": 0.0,
                "mention_count": 0,
                "platform_distribution": defaultdict(int),
                "keyword_distribution": defaultdict(int),
                "top_terms": defaultdict(int),
            }
            asp2[cat] = b

        heat = float(t.get("heat") or 0.0)
        mentions = int(t.get("mentions") or 0)
        sent = float(t.get("sentiment") or 0.0)
        b["heat"] += heat
        b["organic_heat"] += float(t.get("organic_heat") or 0.0)
        b["promo_heat"] += float(t.get("promo_heat") or 0.0)
        b["sentiment_sum"] += sent * float(mentions)
        b["sentiment_weight"] += float(mentions)
        b["mention_count"] += mentions
        b["top_terms"][t.get("name") or ""] += mentions

        for k, v in (t.get("platform_distribution") or {}).items():
            b["platform_distribution"][k] += int(v or 0)
        for k, v in (t.get("keyword_distribution") or {}).items():
            b["keyword_distribution"][k] += int(v or 0)

    topic_aspects: list[dict[str, Any]] = []
    for cat, b in asp2.items():
        avg_sent = (
            (b["sentiment_sum"] / b["sentiment_weight"])
            if b["sentiment_weight"] > 0
            else 0.0
        )
        _heat = float(b["heat"])
        _mc = int(b["mention_count"])
        _score = round(math.log(_heat + 1) * math.log(_mc + 1), 3) if _mc > 0 else 0.0
        topic_aspects.append(
            {
                "category": cat,
                "heat": round(_heat, 2),
                "organic_heat": round(float(b["organic_heat"]), 2),
                "promo_heat": round(float(b["promo_heat"]), 2),
                "sentiment": round(float(avg_sent), 2),
                "mention_count": _mc,
                "score": _score,
                # 该 category 下提及量最多的话题名（非搜索关键词）
                "representative_topics": [
                    k
                    for k, _ in sorted(
                        b["top_terms"].items(), key=lambda x: x[1], reverse=True
                    )[:6]
                    if k
                ],
                "platform_distribution": dict(b["platform_distribution"]),
                "keyword_distribution": dict(b["keyword_distribution"]),
            }
        )
    topic_aspects.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # 3) unmet_needs：按“负面 + 覆盖面广”的代理指标筛选（跨平台/跨关键词更像‘行业共性问题’）
    unmet_candidates: list[dict[str, Any]] = []
    for x in pains:
        if not x.get("name"):
            continue
        p_dist = (
            x.get("platform_distribution")
            if isinstance(x.get("platform_distribution"), dict)
            else {}
        )
        k_dist = (
            x.get("keyword_distribution")
            if isinstance(x.get("keyword_distribution"), dict)
            else {}
        )
        p_cov = len([k for k, v in p_dist.items() if int(v or 0) > 0])
        k_cov = len([k for k, v in k_dist.items() if int(v or 0) > 0])
        coverage = p_cov + k_cov
        try:
            heat = float(x.get("heat") or 0.0)
        except Exception:
            heat = 0.0
        try:
            mentions = int(x.get("mentions") or 0)
        except Exception:
            mentions = 0
        # 经验阈值：覆盖面与样本量都要过线，避免把长尾痛点误判为“行业共性”
        if coverage < 3 or mentions < 5:
            continue
        unmet_candidates.append(
            {
                "name": x.get("name"),
                "category": x.get("category"),
                "heat": heat,
                "organic_heat": x.get("organic_heat"),
                "mentions": mentions,
                "sentiment": x.get("sentiment"),
                "organic_sentiment": x.get("organic_sentiment"),
                "promo_sentiment": x.get("promo_sentiment"),
                "spam_distribution": x.get("spam_distribution"),
                "coverage": coverage,
                "platform_coverage": p_cov,
                "keyword_coverage": k_cov,
                "original_terms": (x.get("original_terms") or [])[:10],
                "post_ids_sample": x.get("post_ids_sample") or [],
                "source_tasks": x.get("source_tasks") or [],
            }
        )
    # 优先按有机热度排序（行业共性痛点应以真实用户声音为准）；回退到总热度
    unmet_candidates.sort(
        key=lambda d: (
            float(d.get("organic_heat") or d.get("heat") or 0.0),
            int(d.get("coverage") or 0),
        ),
        reverse=True,
    )
    unmet_needs = unmet_candidates[:10]

    intent = {
        "topic_radar": {
            "pains": pains[:40],
            "gains": gains[:40],
            "controversies": controversies[:40],
        },
        "unmet_needs": unmet_needs,
        "topic_aspects": topic_aspects[:50],
    }

    # ===== Focus layer (conditional) =====
    focus = None
    if subject:
        # 优先使用 Stage2 对齐后的 role（Target/Competitor）
        targets = [
            e for e in entities_aligned if _norm_role((e or {}).get("role")) == "Target"
        ]
        competitors = [
            e
            for e in entities_aligned
            if _norm_role((e or {}).get("role")) == "Competitor"
        ]

        # 基于 drivers matrix 做维度级对比（若缺失则降级为仅返回候选列表）
        drivers_matrix = (
            (drivers or {}).get("entity_matrix") if isinstance(drivers, dict) else None
        )
        focus = {
            "subject": subject,
            "targets": [
                t.get("name")
                for t in targets[:10]
                if isinstance(t, dict) and t.get("name")
            ],
            "competitors": [
                c.get("name")
                for c in competitors[:10]
                if isinstance(c, dict) and c.get("name")
            ],
            "swot": None,
            "platform_scissors": None,
            "product_line_health": None,  # 产品线健康度
            "gap": None,
        }
        # --- 平台剪刀差：目标阵地分布 vs 行业整体分布 ---
        # 优先用去重后口径（与实体 platform_distribution 一致），旧快照降级到原始任务量
        _upv = overview_safe.get("unique_platform_volume")
        _pv = overview_safe.get("platform_volume")
        industry_platform = (
            _upv
            if isinstance(_upv, dict) and _upv
            else _pv
            if isinstance(_pv, dict)
            else {}
        )
        if not industry_platform:
            # fallback：用实体 platform_distribution 聚合一个“行业分布”近似
            tmp = defaultdict(int)
            for e in entities_aligned or []:
                if not isinstance(e, dict):
                    continue
                for k, v in (e.get("platform_distribution") or {}).items():
                    tmp[str(k)] += int(v or 0)
            industry_platform = dict(tmp)

        subject_platform = defaultdict(int)
        for e in targets:
            if not isinstance(e, dict):
                continue
            for k, v in (e.get("platform_distribution") or {}).items():
                subject_platform[str(k)] += int(v or 0)

        total_industry = sum(int(v or 0) for v in industry_platform.values())
        total_subject = sum(int(v or 0) for v in subject_platform.values())
        if total_industry > 0 and total_subject > 0:
            rows = []
            all_keys = sorted(
                set(industry_platform.keys()) | set(subject_platform.keys())
            )
            for p in all_keys:
                sv = int(subject_platform.get(p, 0))
                iv = int(industry_platform.get(p, 0))
                s_share = sv / float(total_subject) if total_subject > 0 else 0.0
                i_share = iv / float(total_industry) if total_industry > 0 else 0.0
                rows.append(
                    {
                        "platform": p,
                        "subject_mentions": sv,
                        "industry_mentions": iv,
                        "subject_share": round(s_share, 4),
                        "industry_share": round(i_share, 4),
                        "delta": round(s_share - i_share, 4),
                    }
                )
            rows.sort(key=lambda r: abs(float(r.get("delta") or 0.0)), reverse=True)
            focus["platform_scissors"] = {
                "subject_total_mentions": total_subject,
                "industry_total_mentions": total_industry,
                "by_platform": rows[:10],
            }

        # --- 产品线健康度：下钻分析 Subject 旗下的子实体 ---
        # 筛选 parent == subject 的子实体（产品线成员）
        subject_lower = subject.lower()
        product_line_members: list[dict[str, Any]] = []
        total_target_heat = sum(float(t.get("heat") or 0.0) for t in targets)

        for e in entities_aligned or []:
            if not isinstance(e, dict):
                continue
            parent = str(e.get("parent") or "").strip()
            name = str(e.get("name") or "").strip()
            if not name:
                continue
            # 条件：parent 匹配 subject（不区分大小写）
            # 排除 subject 自身（parent == "Self" 或 parent == subject 且 name == subject）
            parent_lower = parent.lower()
            name_lower = name.lower()
            is_child = parent_lower == subject_lower and name_lower != subject_lower
            if not is_child:
                continue

            # 计算声量贡献度
            heat = float(e.get("heat") or 0.0)
            contribution = (heat / total_target_heat) if total_target_heat > 0 else 0.0

            # 获取情感净值：优先使用实体自身的 sentiment 字段
            try:
                sentiment = float(e.get("sentiment") or 0.0)
            except Exception:
                sentiment = 0.0

            # 获取 Top 1 痛点
            top_pain = ""
            top_issues = e.get("top_issues") or []
            if isinstance(top_issues, list) and top_issues:
                first_issue = top_issues[0]
                if isinstance(first_issue, dict):
                    top_pain = str(first_issue.get("text") or "")
                elif isinstance(first_issue, str):
                    top_pain = first_issue

            organic_sentiment = e.get("organic_sentiment")
            if organic_sentiment is not None:
                try:
                    organic_sentiment = round(float(organic_sentiment), 2)
                except Exception:
                    organic_sentiment = None

            product_line_members.append(
                {
                    "name": name,
                    "heat": round(heat, 3),
                    "mentions": int(e.get("mentions") or 0),
                    "contribution": round(contribution, 4),
                    "sentiment": round(sentiment, 2),
                    "organic_sentiment": organic_sentiment,
                    "top_pain": top_pain,
                    "platform_distribution": e.get("platform_distribution") or {},
                    "keyword_distribution": e.get("keyword_distribution") or {},
                    "spam_distribution": e.get("spam_distribution"),
                    "post_ids_sample": e.get("post_ids_sample") or [],
                    "source_tasks": e.get("source_tasks") or [],
                }
            )

        # 按声量贡献度排序
        product_line_members.sort(
            key=lambda x: x.get("contribution", 0.0), reverse=True
        )

        if product_line_members:
            focus["product_line_health"] = {
                "subject": subject,
                "total_heat": round(total_target_heat, 3),
                "members": product_line_members[:20],
            }

        # --- Gap / SWOT：基于 drivers_matrix 的维度级差异（结构化可追溯）---
        if isinstance(drivers_matrix, list) and drivers_matrix:
            min_mentions = 5
            try:
                min_mentions = int((drivers or {}).get("min_cell_mentions") or 5)
            except Exception:
                min_mentions = 5

            target_names = {
                str(t.get("name"))
                for t in targets
                if isinstance(t, dict) and t.get("name")
            }
            comp_names = {
                str(c.get("name"))
                for c in competitors
                if isinstance(c, dict) and c.get("name")
            }

            dim_agg: dict[str, dict[str, float]] = {}
            # 证据聚合：维度 -> {target/comp} 的帖子样本与原话（样本口径）
            max_post_ids_sample = 50

            def _merge_post_samples(dst: dict[str, Any], refs: Any) -> None:
                if not isinstance(refs, list) or not refs:
                    return
                s = dst.setdefault("_post_set", set())
                arr = dst.setdefault("post_ids_sample", [])
                if not isinstance(arr, list):
                    arr = []
                    dst["post_ids_sample"] = arr
                for r in refs:
                    if len(arr) >= max_post_ids_sample:
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
                    if key in s:
                        continue
                    s.add(key)
                    arr.append({"task_id": tid, "post_id": pid})

            def _merge_original_terms(dst: dict[str, Any], terms: Any) -> None:
                if not isinstance(terms, list) or not terms:
                    return
                mp = dst.setdefault("original_terms_counts", {})
                if not isinstance(mp, dict):
                    mp = {}
                    dst["original_terms_counts"] = mp
                for ot in terms:
                    if not isinstance(ot, dict):
                        continue
                    text = (ot.get("text") or "").strip()
                    if not text:
                        continue
                    if len(text) > 100:
                        text = text[:100]
                    try:
                        cnt = int(ot.get("count") or 0)
                    except Exception:
                        cnt = 0
                    if cnt <= 0:
                        cnt = 1
                    mp[text] = int(mp.get(text, 0)) + cnt

            def _finalize_evidence(evd: dict[str, Any]) -> dict[str, Any]:
                if not isinstance(evd, dict):
                    return {"post_ids_sample": [], "original_terms": []}
                evd.pop("_post_set", None)
                counts = evd.pop("original_terms_counts", {})
                if not isinstance(counts, dict):
                    counts = {}
                return {
                    "post_ids_sample": (evd.get("post_ids_sample") or [])[
                        :max_post_ids_sample
                    ],
                    "original_terms": [
                        {"text": t, "count": c}
                        for t, c in sorted(
                            counts.items(),
                            key=lambda x: (len(str(x[0] or "")), int(x[1] or 0)),
                            reverse=True,
                        )[:20]
                    ],
                }

            dim_evidence: dict[str, dict[str, Any]] = {}

            def _acc(
                which: str,
                dim: str,
                sent: float,
                m: int,
                spam_dist: Any = None,
                cell_org_sent: float | None = None,
                cell_promo_sent: float | None = None,
                cell_org_m: int = 0,
                cell_promo_m: int = 0,
            ) -> None:
                if not dim or m <= 0:
                    return
                rec = dim_agg.setdefault(
                    dim,
                    {
                        "target_sent_sum": 0.0,
                        "target_m": 0.0,
                        "comp_sent_sum": 0.0,
                        "comp_m": 0.0,
                        "target_org_sent_sum": 0.0,
                        "target_org_m": 0.0,
                        "target_promo_sent_sum": 0.0,
                        "target_promo_m": 0.0,
                        "comp_org_sent_sum": 0.0,
                        "comp_org_m": 0.0,
                        "comp_promo_sent_sum": 0.0,
                        "comp_promo_m": 0.0,
                        "target_spam_high_post": 0,
                        "target_spam_high_comment": 0,
                        "target_spam_low_post": 0,
                        "target_spam_low_comment": 0,
                        "target_has_spam": False,
                        "comp_spam_high_post": 0,
                        "comp_spam_high_comment": 0,
                        "comp_spam_low_post": 0,
                        "comp_spam_low_comment": 0,
                        "comp_has_spam": False,
                    },
                )
                if which == "target":
                    rec["target_sent_sum"] += sent * float(m)
                    rec["target_m"] += float(m)
                    if cell_org_sent is not None and cell_org_m > 0:
                        rec["target_org_sent_sum"] += cell_org_sent * float(cell_org_m)
                        rec["target_org_m"] += float(cell_org_m)
                    if cell_promo_sent is not None and cell_promo_m > 0:
                        rec["target_promo_sent_sum"] += cell_promo_sent * float(
                            cell_promo_m
                        )
                        rec["target_promo_m"] += float(cell_promo_m)
                    if isinstance(spam_dist, dict):
                        hs = spam_dist.get("high_spam")
                        ls = spam_dist.get("low_spam")
                        if isinstance(hs, dict) and isinstance(ls, dict):
                            rec["target_spam_high_post"] += int(hs.get("post") or 0)
                            rec["target_spam_high_comment"] += int(
                                hs.get("comment") or 0
                            )
                            rec["target_spam_low_post"] += int(ls.get("post") or 0)
                            rec["target_spam_low_comment"] += int(
                                ls.get("comment") or 0
                            )
                            rec["target_has_spam"] = True
                else:
                    rec["comp_sent_sum"] += sent * float(m)
                    rec["comp_m"] += float(m)
                    if cell_org_sent is not None and cell_org_m > 0:
                        rec["comp_org_sent_sum"] += cell_org_sent * float(cell_org_m)
                        rec["comp_org_m"] += float(cell_org_m)
                    if cell_promo_sent is not None and cell_promo_m > 0:
                        rec["comp_promo_sent_sum"] += cell_promo_sent * float(
                            cell_promo_m
                        )
                        rec["comp_promo_m"] += float(cell_promo_m)
                    if isinstance(spam_dist, dict):
                        hs = spam_dist.get("high_spam")
                        ls = spam_dist.get("low_spam")
                        if isinstance(hs, dict) and isinstance(ls, dict):
                            rec["comp_spam_high_post"] += int(hs.get("post") or 0)
                            rec["comp_spam_high_comment"] += int(hs.get("comment") or 0)
                            rec["comp_spam_low_post"] += int(ls.get("post") or 0)
                            rec["comp_spam_low_comment"] += int(ls.get("comment") or 0)
                            rec["comp_has_spam"] = True

            for row in drivers_matrix:
                if not isinstance(row, dict):
                    continue
                en = str(row.get("entity") or "")
                dims = row.get("dimensions") or {}
                if not isinstance(dims, dict):
                    continue
                if en in target_names:
                    which = "target"
                elif en in comp_names:
                    which = "comp"
                else:
                    continue
                for dim, cell in dims.items():
                    if not isinstance(cell, dict):
                        continue
                    try:
                        sent = float(cell.get("sentiment") or 0.0)
                    except Exception:
                        sent = 0.0
                    try:
                        m = int(cell.get("mentions") or 0)
                    except Exception:
                        m = 0
                    spam_dist = cell.get("spam_distribution")
                    cell_org_sent = cell.get("organic_sentiment")
                    cell_promo_sent = cell.get("promo_sentiment")
                    try:
                        cell_org_m = int(cell.get("organic_mentions") or 0)
                    except Exception:
                        cell_org_m = 0
                    try:
                        cell_promo_m = int(cell.get("promo_mentions") or 0)
                    except Exception:
                        cell_promo_m = 0
                    _acc(
                        which,
                        str(dim),
                        sent,
                        m,
                        spam_dist,
                        cell_org_sent,
                        cell_promo_sent,
                        cell_org_m,
                        cell_promo_m,
                    )
                    # evidence merge
                    dim_key = str(dim)
                    evd = dim_evidence.setdefault(dim_key, {"target": {}, "comp": {}})
                    bucket = evd["target"] if which == "target" else evd["comp"]
                    _merge_post_samples(bucket, cell.get("post_ids_sample"))
                    _merge_original_terms(bucket, cell.get("original_terms"))

            strengths: list[dict[str, Any]] = []
            weaknesses: list[dict[str, Any]] = []
            opportunities: list[dict[str, Any]] = []
            threats: list[dict[str, Any]] = []
            gaps: list[dict[str, Any]] = []

            for dim, rec in dim_agg.items():
                tm = float(rec.get("target_m") or 0.0)
                cm = float(rec.get("comp_m") or 0.0)
                ts = (float(rec.get("target_sent_sum") or 0.0) / tm) if tm > 0 else 0.0
                cs = (float(rec.get("comp_sent_sum") or 0.0) / cm) if cm > 0 else 0.0
                delta = ts - cs
                evd = dim_evidence.get(dim) or {}
                target_evd = _finalize_evidence(evd.get("target") or {})
                comp_evd = _finalize_evidence(evd.get("comp") or {})

                # 构建 target 和 competitor 的 spam_distribution
                target_spam_dist = None
                if rec.get("target_has_spam"):
                    thp = int(rec.get("target_spam_high_post") or 0)
                    thc = int(rec.get("target_spam_high_comment") or 0)
                    tlp = int(rec.get("target_spam_low_post") or 0)
                    tlc = int(rec.get("target_spam_low_comment") or 0)
                    target_spam_dist = {
                        "high_spam": {"total": thp + thc, "post": thp, "comment": thc},
                        "low_spam": {"total": tlp + tlc, "post": tlp, "comment": tlc},
                    }

                comp_spam_dist = None
                if rec.get("comp_has_spam"):
                    chp = int(rec.get("comp_spam_high_post") or 0)
                    chc = int(rec.get("comp_spam_high_comment") or 0)
                    clp = int(rec.get("comp_spam_low_post") or 0)
                    clc = int(rec.get("comp_spam_low_comment") or 0)
                    comp_spam_dist = {
                        "high_spam": {"total": chp + chc, "post": chp, "comment": chc},
                        "low_spam": {"total": clp + clc, "post": clp, "comment": clc},
                    }

                def _avg(s: str, w: str) -> float | None:
                    wv = float(rec.get(w) or 0.0)
                    return round(float(rec[s]) / wv, 2) if wv > 0 else None

                item_base = {
                    "dimension": dim,
                    "target_sentiment": round(ts, 2),
                    "competitor_sentiment": round(cs, 2),
                    "target_organic_sentiment": _avg(
                        "target_org_sent_sum", "target_org_m"
                    ),
                    "target_promo_sentiment": _avg(
                        "target_promo_sent_sum", "target_promo_m"
                    ),
                    "competitor_organic_sentiment": _avg(
                        "comp_org_sent_sum", "comp_org_m"
                    ),
                    "competitor_promo_sentiment": _avg(
                        "comp_promo_sent_sum", "comp_promo_m"
                    ),
                    "target_mentions": int(tm),
                    "competitor_mentions": int(cm),
                    "delta": round(delta, 2),
                    "target_spam_distribution": target_spam_dist,
                    "competitor_spam_distribution": comp_spam_dist,
                }

                if tm >= min_mentions and ts >= 0.2 and delta >= 0.15:
                    strengths.append(
                        {
                            **item_base,
                            **target_evd,
                        }
                    )
                if tm >= min_mentions and ts <= -0.2 and delta <= -0.15:
                    weaknesses.append(
                        {
                            **item_base,
                            **target_evd,
                        }
                    )
                if cm >= min_mentions and cs <= -0.2 and ts > -0.1:
                    opportunities.append(
                        {
                            **item_base,
                            **comp_evd,
                        }
                    )
                if cm >= min_mentions and cs >= 0.2 and ts < 0.1:
                    threats.append(
                        {
                            **item_base,
                            **comp_evd,
                        }
                    )

                # Gap：竞品强项明显，但目标在该维度声量缺失（盲点诊断）
                # 有意区别于 Threats（情感劣势）：Gap = 目标根本没覆盖到该维度
                if cm >= min_mentions and cs >= 0.2:
                    low_presence = tm < max(min_mentions, int(cm * 0.3))
                    if low_presence:
                        gaps.append(
                            {
                                **item_base,
                                **comp_evd,
                            }
                        )

            strengths.sort(key=lambda x: x.get("delta", 0.0), reverse=True)
            weaknesses.sort(key=lambda x: x.get("delta", 0.0))
            opportunities.sort(
                key=lambda x: x.get("competitor_mentions", 0), reverse=True
            )
            threats.sort(key=lambda x: x.get("competitor_mentions", 0), reverse=True)
            gaps.sort(
                key=lambda x: (
                    x.get("competitor_mentions", 0),
                    x.get("competitor_sentiment", 0.0),
                ),
                reverse=True,
            )

            focus["swot"] = {
                "strengths": strengths[:10],
                "weaknesses": weaknesses[:10],
                "opportunities": opportunities[:10],
                "threats": threats[:10],
            }
            focus["gap"] = {"dimensions": gaps[:10]}

    return {
        "landscape": landscape,
        "intent": intent,
        "focus": focus,
    }
