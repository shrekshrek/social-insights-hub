"""新闻切片 → Markdown 导出（面向 agent / 知识库）。

按需渲染、不落库：数据已在 NewsSlice.result_data 里，MD 只是它的投影。
投影"二阶计算/聚合/LLM 判断产物"——消费端 LLM 自己拿原始文章重算会算错的那些：
媒体公信力金字塔、实体声量与多维情感、竞争格局 SOV、事件聚类（首发/时间锚/tier 加权热度）、
分级引语、报道与情感时间线、跨任务重叠。这些都依赖本次分析的 per-article LLM 打标，
下游没有原始标注无法复现。

不含 page_synthesis.briefing（headline/key_findings/risks 散文简报）——那是给业务读者的
叙事、也是 LLM 自己能再生成的解读。
"""

from src.news_media.analysis.models import NewsSlice


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


def _dist(d: object) -> str:
    """计数分布字典转 'k:v、k:v'；非 dict 返回空串"""
    if not isinstance(d, dict):
        return ""
    return "、".join(f"{k}:{v}" for k, v in d.items() if v)


def _front_matter(slice_obj: NewsSlice) -> list[str]:
    """front-matter：供 agent 按 type/subject/monitor 过滤路由。"""
    created = (
        slice_obj.created_at.date().isoformat()
        if getattr(slice_obj, "created_at", None)
        else ""
    )
    competitors = [c for c in (slice_obj.competitors or []) if c]
    lines = ["---", "type: news_slice", f"id: {slice_obj.id}"]
    lines.append(f"monitor_id: {slice_obj.monitor_id}")
    lines.append(f"name: {slice_obj.name or ''}")
    if slice_obj.subject:
        lines.append(f"subject: {slice_obj.subject}")
    if competitors:
        lines.append(f"competitors: [{', '.join(competitors)}]")
    lines += [f"status: {slice_obj.status}", f"created_at: {created}", "---", ""]
    return lines


def _overview(descriptive: dict) -> list[str]:
    """概览（报道量 + 各类分布 + 整体情感，二阶聚合）。"""
    if not descriptive:
        return []
    rows = [
        ("报道总量", descriptive.get("articles_total")),
        ("去重文章数", descriptive.get("articles_unique")),
        ("过滤后文章数", descriptive.get("articles_filtered")),
    ]
    rows = [(k, v) for k, v in rows if v is not None]
    lines = ["## 概览"]
    lines += [f"- {k}：{v}" for k, v in rows]
    if descriptive.get("sentiment_overall") is not None:
        lines.append(
            f"- 整体情感：{_fmt_sentiment(descriptive.get('sentiment_overall'))}"
        )
    for label, key in (
        ("媒体层级分布", "source_tier_distribution"),
        ("文章类型分布", "article_type_distribution"),
        ("情感分布", "sentiment_distribution"),
    ):
        txt = _dist(descriptive.get(key))
        if txt:
            lines.append(f"- {label}：{txt}")
    lines.append("")
    return lines


def _media_pyramid(media_landscape: dict) -> list[str]:
    """媒体金字塔（按公信力 tier rollup + 全局头部媒体）——新闻独有二阶结构。"""
    pyramid = media_landscape.get("source_pyramid") or []
    top_sources = media_landscape.get("top_sources") or []
    if not pyramid and not top_sources:
        return []
    lines = ["## 媒体金字塔（按公信力 tier）"]
    for p in pyramid:
        parts = [f"**{p.get('tier', '')}**"]
        if p.get("article_count") is not None:
            parts.append(f"文章 {p['article_count']}")
        if p.get("sentiment_avg") is not None:
            parts.append(f"情感 {_fmt_sentiment(p.get('sentiment_avg'))}")
        line = "- " + "，".join(parts)
        tops = [s for s in (p.get("top_source_names") or []) if s][:3]
        if tops:
            line += "；头部：" + "、".join(tops)
        lines.append(line)
    if top_sources:
        lines.append(
            "- 全局头部媒体："
            + "、".join(
                f"{s.get('name', '')} {_pct(s.get('share'))}" for s in top_sources[:5]
            )
        )
    lines.append("")
    return lines


def _entities(entities: list) -> list[str]:
    """实体（提及/来源数 + 多维情感 + role，二阶）。"""
    if not entities:
        return []
    lines = ["## 实体（按提及）"]
    for e in entities[:25]:
        head = f"**{e.get('name', '')}**"
        if e.get("role"):
            head += f"（{e['role']}）"
        parts = [head]
        if e.get("mention_count") is not None:
            parts.append(f"提及 {e['mention_count']}")
        if e.get("source_count") is not None:
            parts.append(f"来源 {e['source_count']}")
        if e.get("sentiment_avg") is not None:
            parts.append(f"情感 {_fmt_sentiment(e.get('sentiment_avg'))}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _competitive(competitive: dict) -> list[str]:
    """竞争格局（players tier 加权 SOV + 情感 + 引语份额，二阶）。"""
    players = competitive.get("players") or []
    if not players:
        return []
    qs = {q.get("name"): q for q in (competitive.get("quote_share") or [])}
    lines = ["## 竞争格局（主体 vs 竞品）"]
    for p in players:
        head = f"**{p.get('name', '')}**"
        if p.get("role"):
            head += f"（{p['role']}）"
        parts = [head]
        if p.get("tier_weighted_sov") is not None:
            parts.append(f"加权SOV {_pct(p.get('tier_weighted_sov'))}")
        if p.get("mention_count") is not None:
            parts.append(f"提及 {p['mention_count']}")
        if p.get("sentiment_avg") is not None:
            parts.append(f"情感 {_fmt_sentiment(p.get('sentiment_avg'))}")
        q = qs.get(p.get("name")) or {}
        if q.get("quote_count"):
            parts.append(
                f"引语 {q['quote_count']}（官方 {q.get('official_quote_count', 0)}）"
            )
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _event_clusters(event_clusters: list, event_titles: dict) -> list[str]:
    """事件聚类（首发媒体 / 时间锚 / tier 加权热度）——新闻独有二阶结构。"""
    if not event_clusters:
        return []
    lines = ["## 事件聚类（按 tier 加权热度）"]
    for c in event_clusters[:15]:
        cid = str(c.get("cluster_id"))
        label = ((event_titles.get(cid) or {}).get("title")) or f"事件 {cid}"
        parts = [f"**{label}**"]
        if c.get("article_count") is not None:
            parts.append(f"文章 {c['article_count']}")
        fr = c.get("first_reporter") or {}
        if fr.get("source_name"):
            parts.append(f"首发 {fr['source_name']}")
        if c.get("first_reported_at"):
            parts.append(f"首报 {str(c['first_reported_at'])[:10]}")
        if c.get("peak_date"):
            parts.append(f"峰值 {str(c['peak_date'])[:10]}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _quotes(quotes: list) -> list[str]:
    """代表性引语（按 speaker_role 分级取样，分级是二阶 LLM 判断）。"""
    if not quotes:
        return []
    order = {"official": 0, "executive": 1, "analyst": 2, "kol": 3, "other": 4}
    ranked = sorted(quotes, key=lambda q: order.get(q.get("speaker_role", "other"), 9))
    lines = ["## 代表性引语"]
    for q in ranked[:15]:
        text = (q.get("quote") or "").strip().replace("\n", " ")
        if not text:
            continue
        if len(text) > 120:
            text = text[:120] + "…"
        head = f"**{q.get('speaker') or '—'}**"
        if q.get("speaker_role"):
            head += f"（{q['speaker_role']}）"
        line = f"- {head}：{text}"
        if q.get("source_name"):
            line += f" —— {q['source_name']}"
        lines.append(line)
    lines.append("")
    return lines


def _timeline(descriptive: dict) -> list[str]:
    """报道时间线（报道量 + tier 加权情感按日，二阶聚合）。"""
    cov = descriptive.get("coverage_timeseries") or []
    sen = descriptive.get("sentiment_timeseries") or []
    if not cov and not sen:
        return []
    sen_by_date = {s.get("date"): s for s in sen}
    lines = ["## 报道时间线"]
    for c in cov[:60]:
        d = c.get("date")
        parts = [f"{d}"]
        if c.get("count") is not None:
            parts.append(f"报道 {c['count']}")
        s = sen_by_date.get(d) or {}
        if s.get("sentiment_avg") is not None:
            parts.append(f"情感 {_fmt_sentiment(s.get('sentiment_avg'))}")
        lines.append("- " + "，".join(parts))
    lines.append("")
    return lines


def _cross_task(descriptive: dict) -> list[str]:
    """跨任务重叠分布（同一 URL 出现在几个采集任务，二阶聚合）。"""
    dist = (descriptive.get("cross_task_overlap") or {}).get("distribution") or {}
    if not dist:
        return []
    return ["## 跨任务重叠", f"- 分布：{_dist(dist)}", ""]


def render_news_slice_md(slice_obj: NewsSlice) -> str:
    """渲染单个新闻切片为 Markdown（front-matter + 二阶计算/聚合事实）。

    调用方需保证 result_data 非空（未完成的切片由端点返回 404）。
    各段落自带 `if 数据存在` 防御，缺失的块自动跳过。
    """
    data = slice_obj.result_data or {}
    descriptive = data.get("descriptive") or {}
    entities = data.get("entities") or []
    quotes = data.get("quotes") or []
    event_clusters = data.get("event_clusters") or []
    media_landscape = data.get("media_landscape") or {}
    competitive = data.get("competitive") or {}
    event_titles = (data.get("page_synthesis") or {}).get("event_titles") or {}

    sections: list[list[str]] = [
        _front_matter(slice_obj),
        [f"# {slice_obj.name or f'新闻切片 {slice_obj.id}'}", ""],
        _overview(descriptive),
        _media_pyramid(media_landscape),
        _entities(entities),
        _competitive(competitive),
        _event_clusters(event_clusters, event_titles),
        _quotes(quotes),
        _timeline(descriptive),
        _cross_task(descriptive),
    ]

    lines: list[str] = []
    for sec in sections:
        if sec:
            lines += sec

    return "\n".join(lines).rstrip() + "\n"
