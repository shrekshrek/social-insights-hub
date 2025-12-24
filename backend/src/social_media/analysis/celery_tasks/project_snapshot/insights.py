from __future__ import annotations

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
    for e in entities_aligned or []:
        try:
            total_heat += float(e.get("heat") or 0.0)
        except Exception:
            continue

    sov_ranking: list[dict[str, Any]] = []
    for e in entities_aligned[:60]:
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
                "mentions": mentions,
                "share": round((heat / total_heat), 6) if total_heat > 0 else 0.0,
                "sentiment": round(sentiment, 2),
                "sentiment_distribution": e.get("sentiment_distribution") or {},
                "platform_distribution": e.get("platform_distribution") or {},
                "post_ids_sample": post_ids_sample,
                "source_tasks": source_tasks,
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
        b = group_bucket.setdefault(group, {"name": group, "heat": 0.0, "mentions": 0})
        try:
            b["heat"] += float(e.get("heat") or 0.0)
        except Exception:
            pass
        try:
            b["mentions"] += int(e.get("mentions") or 0)
        except Exception:
            pass
    group_share = sorted(
        [
            {
                "name": k,
                "heat": round(float(v.get("heat") or 0.0), 3),
                "mentions": int(v.get("mentions") or 0),
            }
            for k, v in group_bucket.items()
        ],
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
        need_sent = not isinstance(overview_safe.get("global_sentiment"), (int, float))
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
                overview_safe["global_sentiment"] = (
                    round((sent_sum / sent_w), 2) if sent_w > 0 else 0.0
                )

    # --- 行业象限 (Industry Quadrant)：Top 50 实体的 [热度 x 情感] 散点图数据 ---
    industry_quadrant: list[dict[str, Any]] = []
    for item in sov_ranking[:50]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        if not name:
            continue
        industry_quadrant.append(
            {
                "name": name,
                "role": item.get("role") or "Context",
                "heat": item.get("heat") or 0.0,
                "sentiment": item.get("sentiment") or 0.0,
                "mentions": item.get("mentions") or 0,
                "post_ids_sample": item.get("post_ids_sample") or [],
                "source_tasks": item.get("source_tasks") or [],
            }
        )

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
        total_mentions = sum(int(v or 0) for v in p_dist.values()) if p_dist else 0
        # 构建各平台占比
        platform_shares: dict[str, float] = {}
        for p in all_platforms_sorted:
            cnt = int(p_dist.get(p) or 0)
            platform_shares[p] = (
                round(cnt / total_mentions, 4) if total_mentions > 0 else 0.0
            )
        platform_dna.append(
            {
                "name": name,
                "role": item.get("role") or "Context",
                "total_mentions": total_mentions,
                "platform_shares": platform_shares,
            }
        )

    landscape = {
        "sov_ranking": sov_ranking,
        "group_share": group_share,
        "industry_quadrant": industry_quadrant,  # 行业象限散点图数据
        "platform_dna": platform_dna,  # 平台阵地 DNA
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
        item = {
            "name": t.get("name") or "",
            "category": t.get("category") or "其他",
            "heat": float(t.get("heat") or 0.0),
            "mentions": int(t.get("mentions") or 0),
            "sentiment": round(sent, 2),
            "platform_distribution": t.get("platform_distribution") or {},
            "keyword_distribution": t.get("keyword_distribution") or {},
            "original_terms": t.get("original_terms") or [],
            "post_ids_sample": t.get("post_ids_sample") or [],
            "source_tasks": t.get("source_tasks") or [],
        }
        # 经验阈值：sentiment<-0.2 视为负向主导，>0.2 视为正向主导
        if sent <= -0.2:
            pains.append(item)
        elif sent >= 0.2:
            gains.append(item)
        else:
            controversies.append(item)

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
        topic_aspects.append(
            {
                "category": cat,
                "heat": round(float(b["heat"]), 2),
                "sentiment": round(float(avg_sent), 2),
                "mention_count": int(b["mention_count"]),
                "top_keywords": [
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
    topic_aspects.sort(key=lambda x: x.get("heat", 0.0), reverse=True)

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
                "mentions": mentions,
                "sentiment": x.get("sentiment"),
                "coverage": coverage,
                "platform_coverage": p_cov,
                "keyword_coverage": k_cov,
                "original_terms": (x.get("original_terms") or [])[:10],
                "post_ids_sample": x.get("post_ids_sample") or [],
                "source_tasks": x.get("source_tasks") or [],
            }
        )
    unmet_candidates.sort(
        key=lambda d: (float(d.get("heat") or 0.0), int(d.get("coverage") or 0)),
        reverse=True,
    )
    unmet_needs = unmet_candidates[:10]

    intent = {
        "topic_radar": {
            "pains": pains[:20],
            "gains": gains[:20],
            "controversies": controversies[:20],
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
        industry_platform = (
            overview_safe.get("platform_volume")
            if isinstance(overview_safe.get("platform_volume"), dict)
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

            product_line_members.append(
                {
                    "name": name,
                    "heat": round(heat, 3),
                    "mentions": int(e.get("mentions") or 0),
                    "contribution": round(contribution, 4),
                    "sentiment": round(sentiment, 2),
                    "top_pain": top_pain,
                    "platform_distribution": e.get("platform_distribution") or {},
                    "keyword_distribution": e.get("keyword_distribution") or {},
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

            def _acc(which: str, dim: str, sent: float, m: int) -> None:
                if not dim or m <= 0:
                    return
                rec = dim_agg.setdefault(
                    dim,
                    {
                        "target_sent_sum": 0.0,
                        "target_m": 0.0,
                        "comp_sent_sum": 0.0,
                        "comp_m": 0.0,
                    },
                )
                if which == "target":
                    rec["target_sent_sum"] += sent * float(m)
                    rec["target_m"] += float(m)
                else:
                    rec["comp_sent_sum"] += sent * float(m)
                    rec["comp_m"] += float(m)

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
                    _acc(which, str(dim), sent, m)
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

                item_base = {
                    "dimension": dim,
                    "target_sentiment": round(ts, 2),
                    "competitor_sentiment": round(cs, 2),
                    "target_mentions": int(tm),
                    "competitor_mentions": int(cm),
                    "delta": round(delta, 2),
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

                # Gap：竞品强项明显，但目标缺失/偏弱（用于“差异化诊断”）
                if cm >= min_mentions and cs >= 0.2:
                    low_presence = tm < max(min_mentions, int(cm * 0.3))
                    weak_sent = ts < 0.1
                    if low_presence or weak_sent:
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
