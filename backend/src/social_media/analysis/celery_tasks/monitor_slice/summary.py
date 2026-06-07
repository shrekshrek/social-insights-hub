from __future__ import annotations

import json
import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import (
    invoke_chain_with_stats_sync,
)
from src.llm.chains.social.monitor_slice_reports_chain import (
    create_monitor_slice_focus_report_chain,
    create_monitor_slice_landscape_report_chain,
    create_monitor_slice_topic_report_chain,
    parse_monitor_slice_report_response,
)

logger = logging.getLogger(__name__)


def _json_str(obj: Any, max_chars: int) -> str:
    """将对象序列化为 JSON 字符串后截断。

    比 str()[:N] 更安全：产出合法 UTF-8 文本，不含 Python repr 特殊语法，
    LLM 能更好地解析截断后的内容。
    """
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)[:max_chars]
    except Exception:
        return str(obj)[:max_chars]


def _extract_original_terms(items: list[dict[str, Any]], limit: int = 30) -> str:
    """从实体/话题列表中提取 original_terms 作为证据。"""
    terms: list[str] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        ots = item.get("original_terms") or []
        for ot in ots[:3]:
            if isinstance(ot, dict):
                text = ot.get("text") or ""
                if text:
                    terms.append(f"[{name}] {text}")
        if len(terms) >= limit:
            break
    return "\n".join(terms[:limit]) if terms else "（无原话数据）"


def _extract_topic_terms_by_type(
    intent_layer: dict[str, Any], topic_type: str, limit: int = 20
) -> str:
    """从 intent layer 提取指定类型话题的 original_terms。"""
    radar = intent_layer.get("topic_radar") or {}
    items = radar.get(topic_type) or []
    return _extract_original_terms(items, limit)


def _extract_entity_terms_by_role_sentiment(
    entities: list[dict[str, Any]],
    role: str,
    sentiment_filter: str,  # "positive" or "negative"
    limit: int = 15,
) -> str:
    """从实体列表中提取指定角色+情感方向的 original_terms。"""
    terms: list[str] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        e_role = (e.get("role") or "").lower()
        if role.lower() not in e_role:
            continue
        sent = float(e.get("sentiment") or 0.0)
        if sentiment_filter == "positive" and sent < 0.1:
            continue
        if sentiment_filter == "negative" and sent > -0.1:
            continue
        name = e.get("name") or ""
        ots = e.get("original_terms") or []
        for ot in ots[:3]:
            if isinstance(ot, dict):
                text = ot.get("text") or ""
                if text:
                    terms.append(f"[{name}] {text}")
        if len(terms) >= limit:
            break
    return "\n".join(terms[:limit]) if terms else "（无原话数据）"


def _pick(d: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """投影：只保留指定 key（缺失/None 跳过）。用于剥离冗余子结构
    （spam/platform/keyword_distribution、post_ids_sample 等），保留全部分析信号字段。

    注意：这是「信号质量」过滤，不是「省 token」——输入受上下文窗口约束（V4 余量充裕），
    剥离的是会稀释 LLM 注意力的噪声，而非有分析价值的深度字段。
    """
    return {k: d[k] for k in keys if k in d and d[k] is not None}


def _compact_entity_matrix(
    matrix_rows: list[dict[str, Any]],
    dimensions_top: list[str],
    focus_names: set[str],
    max_rows: int = 12,
) -> list[dict[str, Any]]:
    """维度情感矩阵压缩：聚焦行（主体+竞品；无匹配退回前若干行）× top8 维度，单元格取 sentiment/mentions。"""
    dims = [d for d in (dimensions_top or []) if d][:8]
    rows = [r for r in (matrix_rows or []) if isinstance(r, dict)]
    if not rows or not dims:
        return []
    if focus_names:
        rows = [r for r in rows if r.get("entity") in focus_names] or rows[:max_rows]
    else:
        rows = rows[:max_rows]
    out: list[dict[str, Any]] = []
    for r in rows[:max_rows]:
        cells = r.get("dimensions") or {}
        dim_vals = {
            d: {
                "sentiment": cells[d].get("sentiment"),
                "mentions": cells[d].get("mentions"),
            }
            for d in dims
            if isinstance(cells.get(d), dict) and cells[d].get("sentiment") is not None
        }
        if dim_vals:
            out.append({"entity": r.get("entity"), "dimensions": dim_vals})
    return out


_OVERVIEW_KEYS = (
    "total_volume",
    "unique_posts",
    "global_nsr",
    "organic_nsr",
    "promo_nsr",
    "total_organic_heat",
    "total_promo_heat",
    "platform_volume",
)
_SOV_KEYS = (
    "name",
    "parent",
    "role",
    "share",
    "mentions",
    "heat",
    "organic_heat",
    "promo_heat",
    "sentiment",
    "organic_sentiment",
    "promo_sentiment",
)
_GROUP_KEYS = (
    "name",
    "role",
    "share",
    "mentions",
    "heat",
    "organic_heat",
    "promo_heat",
)
_QUADRANT_KEYS = (
    "name",
    "role",
    "heat",
    "organic_heat",
    "promo_heat",
    "sentiment",
    "organic_sentiment",
    "promo_sentiment",
    "mentions",
)


def _time_trend(landscape: dict[str, Any]) -> dict[str, Any]:
    """时序趋势投影：报道量按日 + freshness 概要，剥离每日 post_ids（一阶指针）。

    landscape prompt 第 3 节要写「关键趋势」，原先没喂任何时序数据；此投影补上。
    """
    td = landscape.get("time_distribution") or {}
    dist = [
        {"date": d.get("date"), "count": d.get("count")}
        for d in (td.get("distribution") or [])
        if isinstance(d, dict) and d.get("date")
    ]
    out: dict[str, Any] = {}
    if dist:
        out["by_day"] = dist[-60:]
    if td.get("freshness"):
        out["freshness"] = td["freshness"]
    return out


def _landscape_brief(
    landscape: dict[str, Any],
    entity_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    """大盘层精挑投影：替代整层直灌，避免 sov_ranking 撑满预算后静默截断后排产物。

    保留各产物全部分析信号（含有机/推广拆分）；仅剥离 sov 每项的 platform_distribution
    （与 platform_dna 重复）。补 time_trend（趋势）。item 上限放宽以用足输入余量。
    """
    brief: dict[str, Any] = {
        "overview": _pick(landscape.get("overview") or {}, _OVERVIEW_KEYS),
        "sov_ranking": [
            _pick(r, _SOV_KEYS)
            for r in (landscape.get("sov_ranking") or [])[:30]
            if isinstance(r, dict)
        ],
        "group_share": [
            _pick(g, _GROUP_KEYS)
            for g in (landscape.get("group_share") or [])[:20]
            if isinstance(g, dict)
        ],
        "industry_quadrant": [
            _pick(q, _QUADRANT_KEYS)
            for q in (landscape.get("industry_quadrant") or [])[:25]
            if isinstance(q, dict)
        ],
    }
    if entity_matrix:
        brief["entity_dimension_matrix"] = entity_matrix
    trend = _time_trend(landscape)
    if trend:
        brief["time_trend"] = trend
    return {k: v for k, v in brief.items() if v}


_TOPIC_KEYS = (
    "name",
    "category",
    "heat",
    "organic_heat",
    "promo_heat",
    "mentions",
    "sentiment",
    "organic_sentiment",
    "promo_sentiment",
    "positive_mentions",
    "negative_mentions",
    "polar_total",
    "controversy_depth",
)
_ASPECT_KEYS = (
    "category",
    "heat",
    "organic_heat",
    "promo_heat",
    "sentiment",
    "mention_count",
)


def _topic_brief(intent: dict[str, Any]) -> dict[str, Any]:
    """话题层精挑投影：topic_radar 三类（保留极化深度 controversy_depth/polar_total）
    + unmet_needs + topic_aspects。剥离 spam/platform/keyword_distribution、original_terms
    （走专用 slot）、post_ids_sample 等冗余/已另喂字段。
    """
    radar = intent.get("topic_radar") or {}

    def _slim(items: Any) -> list[dict[str, Any]]:
        return [
            _pick(t, _TOPIC_KEYS) for t in (items or [])[:25] if isinstance(t, dict)
        ]

    brief: dict[str, Any] = {
        "topic_radar": {
            k: _slim(radar.get(k))
            for k in ("pains", "gains", "controversies")
            if radar.get(k)
        },
        "unmet_needs": _slim(intent.get("unmet_needs") or []),
        "topic_aspects": [
            {
                **_pick(a, _ASPECT_KEYS),
                "representative_topics": (a.get("representative_topics") or [])[:5],
            }
            for a in (intent.get("topic_aspects") or [])[:30]
            if isinstance(a, dict)
        ],
    }
    return {k: v for k, v in brief.items() if v}


# 含 organic/promo 情感拆分：focus prompt「竞品对比口径」要求据此分辨
# 竞品优势是产品实力还是营销驱动（数据由 insights.py 算好，勿在投影层剥掉）
_SWOT_KEYS = (
    "dimension",
    "delta",
    "target_sentiment",
    "competitor_sentiment",
    "target_organic_sentiment",
    "competitor_organic_sentiment",
    "target_promo_sentiment",
    "competitor_promo_sentiment",
    "target_mentions",
    "competitor_mentions",
)
_GAP_KEYS = (
    "dimension",
    "target_sentiment",
    "competitor_sentiment",
    "target_organic_sentiment",
    "competitor_organic_sentiment",
    "target_promo_sentiment",
    "competitor_promo_sentiment",
    "target_mentions",
    "competitor_mentions",
    "delta",
)
_SCISSORS_KEYS = (
    "platform",
    "subject_mentions",
    "industry_mentions",
    "subject_share",
    "industry_share",
    "delta",
)


def _focus_brief(focus: dict[str, Any]) -> dict[str, Any]:
    """聚焦层精挑投影：swot（维度+delta+主体/竞品情感与提及）+ gap + platform_scissors
    + product_line_health。"""
    swot = focus.get("swot") or {}
    swot_brief = {
        k: [_pick(d, _SWOT_KEYS) for d in (dims or [])[:8] if isinstance(d, dict)]
        for k, dims in swot.items()
        if isinstance(dims, list) and dims
    }
    gap_dims = [
        _pick(g, _GAP_KEYS)
        for g in ((focus.get("gap") or {}).get("dimensions") or [])[:12]
        if isinstance(g, dict)
    ]
    scissors = [
        _pick(r, _SCISSORS_KEYS)
        for r in ((focus.get("platform_scissors") or {}).get("by_platform") or [])[:10]
        if isinstance(r, dict)
    ]
    brief: dict[str, Any] = {
        "swot": swot_brief,
        "gap": {"dimensions": gap_dims} if gap_dims else None,
        "platform_scissors": {"by_platform": scissors} if scissors else None,
        "product_line_health": focus.get("product_line_health"),
    }
    return {k: v for k, v in brief.items() if v}


def generate_project_reports(
    *,
    subject: str | None,
    meta: dict[str, Any],
    foundation: dict[str, Any],
    layers: dict[str, Any],
    drivers_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    """Step4：并行生成三份报告（Landscape/Topic/Focus）。

    Focus report 在 subject 为空时跳过，返回 None。subject 由调用方从
    SocialSlice.subject 列读取；meta 是 result_data.meta 内的分析时刻元数据
    （timestamp / scope / weights_used），作为 LLM 的上下文注入。
    """
    subject = (subject or "").strip()

    aligned_entities = (foundation or {}).get("aligned_entities") or []
    aligned_topics = (foundation or {}).get("aligned_topics") or []
    intent_layer = (layers or {}).get("intent") or {}

    token_parts: list[dict[str, Any]] = []
    reports: dict[str, Any] = {
        "landscape_report": None,
        "topic_report": None,
        "focus_report": None,
    }
    llm_used = False

    # 维度情感矩阵压缩：主体 + 竞品角色实体（无 subject 时退回前若干行）× top6 维度
    drivers = (foundation or {}).get("drivers") or {}
    dims_top = drivers.get("dimensions_top") or []
    focus_names = {subject} if subject else set()
    for e in aligned_entities:
        if (
            isinstance(e, dict)
            and "competitor" in (e.get("role") or "").lower()
            and e.get("name")
        ):
            focus_names.add(e["name"])
    landscape_matrix = _compact_entity_matrix(drivers_matrix, dims_top, focus_names)

    try:
        # Landscape: 注入 Top 实体的 original_terms
        landscape_terms = _extract_original_terms(aligned_entities, 30)
        chain = create_monitor_slice_landscape_report_chain()
        resp, stats = invoke_chain_with_stats_sync(
            chain,
            {
                "meta": _json_str(meta, 4000),
                "layers": _json_str(
                    _landscape_brief(
                        (layers or {}).get("landscape") or {},
                        landscape_matrix,
                    ),
                    30000,
                ),
                "top_entities": _json_str(aligned_entities[:40], 9000),
                "original_terms": landscape_terms[:6000],
            },
            "chat",
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        reports["landscape_report"] = parse_monitor_slice_report_response(text)
        token_parts.append(stats or {})
        llm_used = True
    except Exception as e:
        logger.error("[Slice Reports] Landscape report failed: %s", e, exc_info=True)

    try:
        # Topic: 注入 痛点/爽点/未满足需求 的 original_terms
        pains_terms = _extract_topic_terms_by_type(intent_layer, "pains", 20)
        gains_terms = _extract_topic_terms_by_type(intent_layer, "gains", 20)
        unmet_terms = _extract_original_terms(intent_layer.get("unmet_needs") or [], 15)
        chain = create_monitor_slice_topic_report_chain()
        resp, stats = invoke_chain_with_stats_sync(
            chain,
            {
                "meta": _json_str(meta, 4000),
                "layers": _json_str(_topic_brief(intent_layer), 30000),
                "top_topics": _json_str(aligned_topics[:40], 9000),
                "pains_original_terms": pains_terms[:4000],
                "gains_original_terms": gains_terms[:4000],
                "unmet_original_terms": unmet_terms[:3000],
            },
            "chat",
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        reports["topic_report"] = parse_monitor_slice_report_response(text)
        token_parts.append(stats or {})
        llm_used = True
    except Exception as e:
        logger.error("[Slice Reports] Topic report failed: %s", e, exc_info=True)

    if subject:
        try:
            # Focus: 注入目标负面原话 + 竞品正面原话
            target_neg = _extract_entity_terms_by_role_sentiment(
                aligned_entities, "target", "negative", 15
            )
            comp_pos = _extract_entity_terms_by_role_sentiment(
                aligned_entities, "competitor", "positive", 15
            )
            chain = create_monitor_slice_focus_report_chain()
            resp, stats = invoke_chain_with_stats_sync(
                chain,
                {
                    "meta": _json_str(meta, 4000),
                    "layers": _json_str(
                        _focus_brief((layers or {}).get("focus") or {}),
                        30000,
                    ),
                    "drivers_matrix": _json_str((drivers_matrix or [])[:20], 9000),
                    "target_negative_terms": target_neg[:3000],
                    "competitor_positive_terms": comp_pos[:3000],
                },
                "chat",
            )
            text = resp.content if hasattr(resp, "content") else str(resp)
            reports["focus_report"] = parse_monitor_slice_report_response(text)
            token_parts.append(stats or {})
            llm_used = True
        except Exception as e:
            logger.error("[Slice Reports] Focus report failed: %s", e, exc_info=True)

    # token stats 合并（复用既有工具结构）
    token_usage = {
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
    for st in token_parts:
        if not isinstance(st, dict):
            continue
        s = st.get("summary") if isinstance(st.get("summary"), dict) else {}
        token_usage["summary"]["total_calls"] += int(s.get("total_calls") or 0)
        token_usage["summary"]["total_input_tokens"] += int(
            s.get("total_input_tokens") or 0
        )
        token_usage["summary"]["total_output_tokens"] += int(
            s.get("total_output_tokens") or 0
        )
        token_usage["summary"]["total_tokens"] += int(s.get("total_tokens") or 0)
        token_usage["summary"]["total_cost_cny"] += float(
            s.get("total_cost_cny") or 0.0
        )
        token_usage["summary"]["total_duration_seconds"] += float(
            s.get("total_duration_seconds") or 0.0
        )
        calls = (
            st.get("call_details") if isinstance(st.get("call_details"), list) else []
        )
        token_usage["call_details"].extend([c for c in calls if isinstance(c, dict)])

    ok = bool(reports.get("landscape_report")) and bool(reports.get("topic_report"))
    if subject:
        # Focus 软约束：检查是否包含三段式建议（使用同义词匹配）
        fr = (
            reports.get("focus_report")
            if isinstance(reports.get("focus_report"), dict)
            else {}
        )
        content = (fr or {}).get("content") if isinstance(fr, dict) else ""
        content = str(content or "")

        # 使用同义词列表，更灵活地匹配
        marketing_kw = ["营销", "市场", "Marketing", "推广", "传播"]
        product_kw = ["产品", "Product", "功能", "体验"]
        pr_kw = ["公关", "服务", "PR", "Service", "危机", "舆情"]

        has_marketing = any(kw in content for kw in marketing_kw)
        has_product = any(kw in content for kw in product_kw)
        has_pr = any(kw in content for kw in pr_kw)
        has_required = has_marketing and has_product and has_pr

        # 即使不满足硬约束，也保留报告内容（但标记警告）
        if not has_required and reports.get("focus_report"):
            logger.warning(
                f"[Slice Reports] Focus report missing sections: "
                f"marketing={has_marketing}, product={has_product}, pr={has_pr}"
            )
        # 只要有 focus_report 内容就算成功（移除丢弃逻辑）
        ok = ok and bool(reports.get("focus_report"))

    return {
        "status": "completed" if ok else "failed",
        "llm": {"used": llm_used, "token_stats": token_usage},
        "reports": reports,
        "error": None if ok else ("focus_report_empty" if subject else "empty_reports"),
    }
