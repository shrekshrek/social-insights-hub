"""社媒切片 → Markdown 导出（面向 agent / 知识库）。

按需渲染、不落库：数据已在 SocialSlice.result_data 里，MD 只是它的投影。
只投影"原始聚合事实 + 计算型数值"——实体 / 话题 / 概览数值（LLM 自己重算会算错的）；
不含 Stage3 的 3 份叙事报告（行业格局 / 话题洞察 / 战略诊断），那是 Word 的内容、
也是 LLM 自己能再生成的解读。
"""

from src.social_media.analysis.models import SocialSlice


def _fmt_sentiment(value: object) -> str:
    """情感分转可读（带符号）；非数值返回 '-'"""
    try:
        return f"{float(value):+.2f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"


def render_social_slice_md(slice_obj: SocialSlice) -> str:
    """渲染单个社媒切片为 Markdown（front-matter + 聚合事实 + 数值）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    """
    data = slice_obj.result_data or {}
    insights = data.get("insights") or {}
    overview = ((data.get("layers") or {}).get("landscape") or {}).get("overview") or {}
    metrics = data.get("metrics") or {}
    lines: list[str] = []

    # --- front-matter：供 agent 按 type/subject/monitor 过滤路由 ---
    created = (
        slice_obj.created_at.date().isoformat()
        if getattr(slice_obj, "created_at", None)
        else ""
    )
    competitors = [c for c in (slice_obj.competitors or []) if c]
    lines += ["---", "type: social_slice", f"id: {slice_obj.id}"]
    lines.append(f"monitor_id: {slice_obj.monitor_id}")
    lines.append(f"name: {slice_obj.name or ''}")
    if slice_obj.subject:
        lines.append(f"subject: {slice_obj.subject}")
    if competitors:
        lines.append(f"competitors: [{', '.join(competitors)}]")
    lines += [f"status: {slice_obj.status}", f"created_at: {created}", "---", ""]

    lines += [f"# {slice_obj.name or f'社媒切片 {slice_obj.id}'}", ""]

    # --- 概览数值（计算型，预计算带上，别让 agent 自己算）---
    ov_rows = [
        ("原文总量", overview.get("total_volume")),
        ("去重原文数", overview.get("unique_posts")),
        ("全局 NSR", overview.get("global_nsr")),
        ("有机 NSR", overview.get("organic_nsr")),
        ("推广 NSR", overview.get("promo_nsr")),
    ]
    marketing = metrics.get("marketing_analysis") or {}
    if marketing.get("promotion_ratio") is not None:
        ov_rows.append(("推广占比", marketing.get("promotion_ratio")))
    ov_rows = [(k, v) for k, v in ov_rows if v is not None]
    if ov_rows:
        lines.append("## 概览")
        lines += [f"- {k}：{v}" for k, v in ov_rows]
        platform_vol = overview.get("platform_volume") or {}
        if platform_vol:
            lines.append(
                "- 平台分布：" + "、".join(f"{p}:{n}" for p, n in platform_vol.items())
            )
        lines.append("")

    # --- 实体（聚合事实 + 情感/份额数值）---
    top_entities = insights.get("top_entities") or []
    if top_entities:
        lines.append("## 实体（按声量）")
        for e in top_entities[:30]:
            parts = [f"**{e.get('name', '')}**"]
            if e.get("mentions") is not None:
                parts.append(f"提及 {e['mentions']}")
            if e.get("share") is not None:
                parts.append(f"声量占比 {e['share']}")
            parts.append(f"情感 {_fmt_sentiment(e.get('sentiment'))}")
            lines.append("- " + "，".join(parts))
        lines.append("")

    # --- 实体角色（主体 / 竞品）---
    target = [
        e.get("name", "")
        for e in (insights.get("target_entities") or [])
        if e.get("name")
    ]
    competitor = [
        e.get("name", "")
        for e in (insights.get("competitor_entities") or [])
        if e.get("name")
    ]
    if target or competitor:
        lines.append("## 实体角色")
        if target:
            lines.append(f"- 主体：{'、'.join(target)}")
        if competitor:
            lines.append(f"- 竞品：{'、'.join(competitor)}")
        lines.append("")

    # --- 话题与观点（聚合事实）---
    top_topics = insights.get("top_topics") or []
    if top_topics:
        lines.append("## 话题与观点")
        for t in top_topics[:40]:
            parts = [f"**{t.get('name', '')}**"]
            if t.get("mentions") is not None:
                parts.append(f"提及 {t['mentions']}")
            if t.get("post_source_count") is not None:
                parts.append(f"源帖 {t['post_source_count']}")
            if t.get("sentiment") is not None:
                parts.append(f"情感 {_fmt_sentiment(t.get('sentiment'))}")
            lines.append("- " + "，".join(parts))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
