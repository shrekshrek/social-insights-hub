from __future__ import annotations

import logging
from typing import Any

from src.social_media.analysis.celery_tasks.llm_utils import (
    invoke_chain_with_stats_sync,
)
from src.langchain.chains.project_slice_reports_chain import (
    create_project_slice_focus_report_chain,
    create_project_slice_landscape_report_chain,
    create_project_slice_topic_report_chain,
    parse_project_slice_report_response,
)

logger = logging.getLogger(__name__)


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


def generate_project_reports(
    *,
    meta: dict[str, Any],
    foundation: dict[str, Any],
    layers: dict[str, Any],
    drivers_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    """Step4：并行生成三份报告（Landscape/Topic/Focus）。

    Focus report 在 meta.subject 为空时跳过，返回 None。
    """
    subject = (meta or {}).get("subject")
    subject = str(subject).strip() if subject is not None else ""

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

    try:
        # Landscape: 注入 Top 实体的 original_terms
        landscape_terms = _extract_original_terms(aligned_entities, 30)
        chain = create_project_slice_landscape_report_chain()
        resp, stats = invoke_chain_with_stats_sync(
            chain,
            {
                "meta": str(meta)[:4000],
                "layers": str((layers or {}).get("landscape"))[:9000],
                "top_entities": str(aligned_entities[:40])[:9000],
                "original_terms": landscape_terms[:6000],
            },
            "chat",
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        reports["landscape_report"] = parse_project_slice_report_response(text)
        token_parts.append(stats or {})
        llm_used = True
    except Exception as e:
        logger.error(f"[Slice Reports] Landscape report failed: {e}", exc_info=True)

    try:
        # Topic: 注入 痛点/爽点/未满足需求 的 original_terms
        pains_terms = _extract_topic_terms_by_type(intent_layer, "pains", 20)
        gains_terms = _extract_topic_terms_by_type(intent_layer, "gains", 20)
        unmet_terms = _extract_original_terms(intent_layer.get("unmet_needs") or [], 15)
        chain = create_project_slice_topic_report_chain()
        resp, stats = invoke_chain_with_stats_sync(
            chain,
            {
                "meta": str(meta)[:4000],
                "layers": str(intent_layer)[:9000],
                "top_topics": str(aligned_topics[:40])[:9000],
                "pains_original_terms": pains_terms[:4000],
                "gains_original_terms": gains_terms[:4000],
                "unmet_original_terms": unmet_terms[:3000],
            },
            "chat",
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        reports["topic_report"] = parse_project_slice_report_response(text)
        token_parts.append(stats or {})
        llm_used = True
    except Exception as e:
        logger.error(f"[Slice Reports] Topic report failed: {e}", exc_info=True)

    if subject:
        try:
            # Focus: 注入目标负面原话 + 竞品正面原话
            target_neg = _extract_entity_terms_by_role_sentiment(
                aligned_entities, "target", "negative", 15
            )
            comp_pos = _extract_entity_terms_by_role_sentiment(
                aligned_entities, "competitor", "positive", 15
            )
            chain = create_project_slice_focus_report_chain()
            resp, stats = invoke_chain_with_stats_sync(
                chain,
                {
                    "meta": str(meta)[:4000],
                    "layers": str((layers or {}).get("focus"))[:9000],
                    "drivers_matrix": str((drivers_matrix or [])[:20])[:9000],
                    "target_negative_terms": target_neg[:3000],
                    "competitor_positive_terms": comp_pos[:3000],
                },
                "chat",
            )
            text = resp.content if hasattr(resp, "content") else str(resp)
            reports["focus_report"] = parse_project_slice_report_response(text)
            token_parts.append(stats or {})
            llm_used = True
        except Exception as e:
            logger.error(f"[Slice Reports] Focus report failed: {e}", exc_info=True)

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
        "error": None
        if ok
        else ("focus_report_empty" if subject else "empty_reports"),
    }
