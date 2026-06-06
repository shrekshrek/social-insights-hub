"""社媒切片 → Markdown 导出（面向 agent / 知识库）。

按需渲染、不落库：数据已在 SocialSlice.result_data 里，MD 只是它的投影。
投影"原始聚合事实 + 计算型数值"——消费端 LLM 自己拿原始帖子重算会算错的那些：
实体 / 话题的情感与声量、品牌组聚合、平台构成、维度情感矩阵、话题分类、
未满足需求、主体 vs 行业 / 竞品的竞争基准。这些都依赖当初那次 per-post 的
LLM 打标，下游没有原始标注无法复现。

不含 Stage3 的 3 份叙事报告（行业格局 / 话题洞察 / 战略诊断）与 SWOT 定性结论——
那是 Word 的内容、也是 LLM 自己能再生成的解读。
"""

from src.social_media.analysis.models import SocialSlice


def _fmt_sentiment(value: object) -> str:
    """情感分转可读（带符号）；非数值返回 '-'"""
    try:
        return f"{float(value):+.2f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"


def _pct(value: object) -> str:
    """份额（0~1）转百分比；非数值返回 '-'"""
    try:
        return f"{float(value) * 100:.0f}%"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"


def _num(value: object) -> str:
    """整数化；非数值返回 '-'"""
    try:
        return str(int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"


def _td(value: object) -> str:
    """表格单元格转义：去掉竖线/换行，避免破坏 markdown 表格"""
    return str(value or "").replace("|", "／").replace("\n", " ").strip()


def _front_matter(slice_obj: SocialSlice) -> list[str]:
    """front-matter：供 agent 按 type/subject/monitor 过滤路由。"""
    created = (
        slice_obj.created_at.date().isoformat()
        if getattr(slice_obj, "created_at", None)
        else ""
    )
    competitors = [c for c in (slice_obj.competitors or []) if c]
    lines = ["---", "type: social_slice", f"id: {slice_obj.id}"]
    lines.append(f"monitor_id: {slice_obj.monitor_id}")
    lines.append(f"name: {slice_obj.name or ''}")
    if slice_obj.subject:
        lines.append(f"subject: {slice_obj.subject}")
    if competitors:
        lines.append(f"competitors: [{', '.join(competitors)}]")
    lines += [f"status: {slice_obj.status}", f"created_at: {created}", "---", ""]
    return lines


def _overview(landscape: dict, metrics: dict) -> list[str]:
    """概览数值（计算型，预计算带上，别让 agent 自己算）。"""
    overview = landscape.get("overview") or {}
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
    if not ov_rows:
        return []
    lines = ["## 概览"]
    lines += [f"- {k}：{v}" for k, v in ov_rows]
    platform_vol = overview.get("platform_volume") or {}
    if platform_vol:
        lines.append(
            "- 平台分布：" + "、".join(f"{p}:{n}" for p, n in platform_vol.items())
        )
    lines.append("")
    return lines


def _entities(insights: dict) -> list[str]:
    """实体（聚合事实 + 情感/份额数值）。"""
    top_entities = insights.get("top_entities") or []
    if not top_entities:
        return []
    lines = ["## 实体（按声量）"]
    for e in top_entities[:30]:
        parts = [f"**{e.get('name', '')}**"]
        if e.get("mentions") is not None:
            parts.append(f"提及 {e['mentions']}")
        if e.get("share") is not None:
            parts.append(f"声量占比 {e['share']}")
        parts.append(f"情感 {_fmt_sentiment(e.get('sentiment'))}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _entity_roles(insights: dict) -> list[str]:
    """实体角色（主体 / 竞品）。"""
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
    if not target and not competitor:
        return []
    lines = ["## 实体角色"]
    if target:
        lines.append(f"- 主体：{'、'.join(target)}")
    if competitor:
        lines.append(f"- 竞品：{'、'.join(competitor)}")
    lines.append("")
    return lines


def _group_share(landscape: dict) -> list[str]:
    """品牌组声量（按品牌族聚合，需品牌→母品牌映射，下游重算不出来）。"""
    rows = landscape.get("group_share") or []
    if not rows:
        return []
    lines = ["## 品牌组声量（按品牌族聚合）"]
    for g in rows[:15]:
        head = f"**{g.get('name', '')}**"
        if g.get("role"):
            head += f"（{g['role']}）"
        parts = [head]
        if g.get("mentions") is not None:
            parts.append(f"提及 {g['mentions']}")
        if g.get("share") is not None:
            parts.append(f"声量占比 {_pct(g['share'])}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _platform_dna(landscape: dict) -> list[str]:
    """平台阵地（各实体声量的平台构成，需逐帖平台×实体 join）。"""
    rows = landscape.get("platform_dna") or []
    if not rows:
        return []
    lines = ["## 平台阵地（各实体声量的平台构成）"]
    for e in rows[:15]:
        shares = e.get("platform_shares") or {}
        top = [
            (p, s)
            for p, s in sorted(shares.items(), key=lambda kv: kv[1] or 0, reverse=True)
            if s
        ][:5]
        if not top:
            continue
        head = f"**{e.get('name', '')}**"
        if e.get("total_mentions") is not None:
            head += f"（提及 {e['total_mentions']}）"
        lines.append(f"- {head}：" + "、".join(f"{p} {_pct(s)}" for p, s in top))
    lines.append("")
    return lines


def _entity_matrix(drivers: dict) -> list[str]:
    """维度情感矩阵（实体 × 维度，单元格=情感(提及)）——切片里信息密度最高的计算型交叉表。"""
    matrix = drivers.get("entity_matrix") or []
    dims = [d for d in (drivers.get("dimensions_top") or []) if d][:12]
    if not matrix or not dims:
        return []
    lines = ["## 维度情感矩阵（实体 × 维度，单元格=情感(提及)）", ""]
    lines.append("| 实体 | " + " | ".join(_td(d) for d in dims) + " |")
    lines.append("|---|" + "---|" * len(dims))
    for row in matrix[:15]:
        cells = row.get("dimensions") or {}
        vals = []
        for d in dims:
            c = cells.get(d)
            if isinstance(c, dict) and c.get("sentiment") is not None:
                vals.append(
                    f"{_fmt_sentiment(c.get('sentiment'))}({_num(c.get('mentions'))})"
                )
            else:
                vals.append("-")
        lines.append(f"| {_td(row.get('entity'))} | " + " | ".join(vals) + " |")
    lines.append("")
    return lines


def _topics(insights: dict) -> list[str]:
    """话题与观点（聚合事实）。"""
    top_topics = insights.get("top_topics") or []
    if not top_topics:
        return []
    lines = ["## 话题与观点"]
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
    return lines


def _topic_aspects(intent: dict) -> list[str]:
    """话题分类（按分类聚合，需话题→分类映射）。"""
    rows = intent.get("topic_aspects") or []
    if not rows:
        return []
    lines = ["## 话题分类（按分类聚合）"]
    for a in rows[:20]:
        parts = [f"**{a.get('category', '')}**"]
        if a.get("mention_count") is not None:
            parts.append(f"提及 {a['mention_count']}")
        if a.get("sentiment") is not None:
            parts.append(f"情感 {_fmt_sentiment(a.get('sentiment'))}")
        line = "- " + "，".join(parts)
        reps = [r for r in (a.get("representative_topics") or []) if r][:5]
        if reps:
            line += "；代表：" + "、".join(reps)
        lines.append(line)
    lines.append("")
    return lines


def _unmet_needs(intent: dict) -> list[str]:
    """未满足需求（已是 LLM 判断的策展信号）。"""
    rows = intent.get("unmet_needs") or []
    if not rows:
        return []
    lines = ["## 未满足需求"]
    for u in rows[:15]:
        parts = [f"**{u.get('name', '')}**"]
        if u.get("category"):
            parts.append(str(u["category"]))
        if u.get("mentions") is not None:
            parts.append(f"提及 {u['mentions']}")
        if u.get("sentiment") is not None:
            parts.append(f"情感 {_fmt_sentiment(u.get('sentiment'))}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _platform_scissors(focus: dict) -> list[str]:
    """主体 vs 行业·平台剪刀差（份额差，需行业基准）。"""
    rows = (focus.get("platform_scissors") or {}).get("by_platform") or []
    if not rows:
        return []
    lines = ["## 主体 vs 行业·平台剪刀差（份额差）"]
    for r in rows[:10]:
        delta = r.get("delta")
        dtxt = ""
        if isinstance(delta, (int, float)):
            dtxt = f"（{'+' if delta >= 0 else ''}{delta * 100:.0f}pp）"
        lines.append(
            f"- {r.get('platform', '')}：主体 {_pct(r.get('subject_share'))}"
            f" vs 行业 {_pct(r.get('industry_share'))}{dtxt}"
        )
    lines.append("")
    return lines


def _gap(focus: dict) -> list[str]:
    """主体 vs 竞品·维度差距（盲点：竞品强、主体声量缺失）。"""
    dims = (focus.get("gap") or {}).get("dimensions") or []
    if not dims:
        return []
    lines = ["## 主体 vs 竞品·维度差距（盲点）"]
    for d in dims[:10]:
        tm = int(d.get("target_mentions") or 0)
        target = (
            f"{_fmt_sentiment(d.get('target_sentiment'))}（{tm}条）"
            if tm > 0
            else f"—（{tm}条）"
        )
        comp = f"{_fmt_sentiment(d.get('competitor_sentiment'))}（{_num(d.get('competitor_mentions'))}条）"
        lines.append(f"- {d.get('dimension', '')}：主体 {target} vs 竞品 {comp}")
    lines.append("")
    return lines


def render_social_slice_md(slice_obj: SocialSlice) -> str:
    """渲染单个社媒切片为 Markdown（front-matter + 聚合事实 + 计算型数值）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    各段落自带 `if 数据存在` 防御，缺失的层自动跳过。
    """
    data = slice_obj.result_data or {}
    layers = data.get("layers") or {}
    landscape = layers.get("landscape") or {}
    intent = layers.get("intent") or {}
    focus = layers.get("focus") or {}
    drivers = (data.get("foundation") or {}).get("drivers") or {}
    insights = data.get("insights") or {}
    metrics = data.get("metrics") or {}

    sections: list[list[str]] = [
        _front_matter(slice_obj),
        [f"# {slice_obj.name or f'社媒切片 {slice_obj.id}'}", ""],
        _overview(landscape, metrics),
        _entities(insights),
        _entity_roles(insights),
        _group_share(landscape),
        _platform_dna(landscape),
        _entity_matrix(drivers),
        _topics(insights),
        _topic_aspects(intent),
        _unmet_needs(intent),
        _platform_scissors(focus),
        _gap(focus),
    ]

    lines: list[str] = []
    for sec in sections:
        if sec:
            lines += sec

    return "\n".join(lines).rstrip() + "\n"
