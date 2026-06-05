"""专题研究 → Markdown 导出。

按需渲染，不落库：数据已在 ResearchTask.result_data / 列里，MD 只是它的投影。
面向 agent / 知识库消费——带 front-matter（供过滤路由）+ 完整结构化内容 + 来源 URL（可溯源）。
"""

from src.research_agent.models import ResearchTask

_PROFILE_LABELS = {"industry": "行业研究", "creative": "创意研究"}


def render_research_md(task: ResearchTask) -> str:
    """把单个已完成的专题研究任务渲染为 Markdown。

    调用方需保证 task.status == "completed" 且 task.result_data 非空。
    """
    data = task.result_data or {}
    lines: list[str] = []

    # --- front-matter：供 agent 按 type/profile/strategy_id 过滤路由 ---
    created = task.created_at.date().isoformat() if task.created_at else ""
    lines += ["---", "type: research", f"id: {task.id}"]
    lines.append(f"profile: {task.profile_name or 'industry'}")
    lines.append(f"title: {task.title or ''}")
    if task.strategy_id:
        lines.append(f"strategy_id: {task.strategy_id}")
    lines += [f"status: {task.status}", f"created_at: {created}", "---", ""]

    # --- 标题 + 研究主题 + 背景 ---
    profile_label = _PROFILE_LABELS.get(
        task.profile_name or "", task.profile_name or ""
    )
    lines.append(f"# {task.title or task.analysis_goal}")
    lines += [
        "",
        f"**研究类型**：{profile_label}",
        "",
        "## 研究主题",
        task.analysis_goal or "",
        "",
    ]

    context = (task.search_config or {}).get("context", "")
    if context:
        lines += ["## 研究背景", context, ""]

    # --- 综合分析（synthesis 本身就是 markdown）---
    synthesis = (data.get("synthesis") or "").strip()
    if synthesis:
        lines += ["## 综合分析", synthesis, ""]

    # --- 按研究问题的发现（全量结构化）---
    findings_by_question = data.get("findings_by_question") or {}
    if findings_by_question:
        lines += ["## 按研究问题的发现", ""]
        for question, finding in findings_by_question.items():
            finding = finding or {}
            lines.append(f"### {question}")
            if finding.get("confidence"):
                lines.append(f"**置信度**：{finding['confidence']}")
            if finding.get("answer_summary"):
                lines += ["", finding["answer_summary"]]
            data_points = finding.get("data_points") or []
            if data_points:
                lines += ["", "**关键数据**："]
                for dp in data_points:
                    parts = [f"{dp.get('metric', '')}：{dp.get('value', '')}"]
                    if dp.get("period"):
                        parts.append(f"({dp['period']})")
                    if dp.get("source"):
                        parts.append(f"— {dp['source']}")
                    lines.append("- " + " ".join(parts))
            refs = finding.get("source_refs") or []
            if refs:
                lines += ["", f"**来源**：{', '.join(refs)}"]
            lines.append("")

    # --- 信息缺口 ---
    gaps = data.get("information_gaps") or []
    if gaps:
        lines.append("## 信息缺口")
        lines += [f"- {g}" for g in gaps]
        lines.append("")

    # --- 来源清单（带 URL，供 agent 溯源）---
    sources = data.get("sources") or []
    if sources:
        lines.append("## 来源")
        for s in sources:
            meta = "、".join(
                x for x in [s.get("source_tier", ""), s.get("published_date", "")] if x
            )
            meta_str = f"（{meta}）" if meta else ""
            title = s.get("title", "")
            url = s.get("url", "")
            label = f"[{title}]({url})" if url else title
            lines.append(f"- [{s.get('id', '')}] {label}{meta_str}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
