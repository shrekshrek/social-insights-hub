"""Research Agent 数据格式化器 — 按 stage 提取研究发现注入策略 chain prompt

Route B 集成方案：每个 stage chain 的 USER_TEMPLATE 新增 `{research_findings}` 占位符，
本模块提供 per-stage 格式化函数，从 ResearchTask.result_data 中提取适量数据。

数据结构（来自 research_agent/state.py）：
- findings_by_question: dict[question_text, QuestionFinding]
  - QuestionFinding: answer_summary / confidence / data_points / source_refs
  - DataPoint: metric / value / period / source
- synthesis: str（markdown 综合报告）
- information_gaps: list[str]

Token 预算指引：
- Layer 1（Insight / Agenda Map）: ~1.5K tokens — 完整 findings + data_points
- Layer 2（Brand Role / Landscape）: ~800 tokens — synthesis 摘要
- Layer 3（Big Idea / Strategic Brief）: ~400 tokens — 压缩要点
"""

from __future__ import annotations



def _load_result(result_data: dict | None) -> dict:
    """安全提取 result_data 字段"""
    if not result_data or not isinstance(result_data, dict):
        return {}
    return result_data


def format_research_for_insight(result_data: dict | None) -> str:
    """Insight 层（brand_strategy 第 1 层）：完整研究发现

    Insight 需要最丰富的外部证据来发现 Social Tension 和 Brand Opportunity，
    注入 findings_by_question 全量 + information_gaps 作为分析盲区提示。
    """
    rd = _load_result(result_data)
    findings = rd.get("findings_by_question")
    gaps = rd.get("information_gaps")

    if not findings:
        return ""

    parts = [
        "## 行业研究发现（Research Agent）\n",
        "以下数据来自自动化行业研究（搜索引擎 + 行业报告 + 公开数据），"
        "代表**专家/行业视角**，与社媒消费者声音、新闻媒体报道三位一体。\n",
        "### 研究发现（按问题组织）\n",
    ]

    for question, finding in findings.items():
        confidence = finding.get("confidence", "medium")
        parts.append(f"**Q: {question}** (置信度: {confidence})")
        parts.append(f"  答：{finding.get('answer_summary', '')}")

        data_points = finding.get("data_points") or []
        if data_points:
            parts.append("  关键数据：")
            for dp in data_points[:5]:  # 每个问题最多 5 个数据点
                source = dp.get("source", "")
                period = dp.get("period", "")
                suffix = f" ({period}, {source})" if period and source else ""
                parts.append(f"  - {dp.get('metric', '')}: {dp.get('value', '')}{suffix}")
        parts.append("")

    if gaps:
        parts.append("### 信息缺口（分析盲区）\n")
        for gap in gaps[:5]:
            parts.append(f"- {gap}")
        parts.append("")

    return "\n".join(parts)


def format_research_for_brand_role(result_data: dict | None) -> str:
    """Brand Role 层（brand_strategy 第 2 层）：synthesis 摘要 + 关键数据

    Brand Role 基于 Insight 结果推导角色，需要行业背景验证竞争定位，
    注入 synthesis 全文（已是 markdown 摘要）+ high-confidence 数据点。
    """
    rd = _load_result(result_data)
    synthesis = rd.get("synthesis", "")
    findings = rd.get("findings_by_question")

    if not synthesis and not findings:
        return ""

    parts = [
        "## 行业研究背景（Research Agent）\n",
        "以下为行业研究的综合分析，供品牌角色推导时参考竞争格局和市场趋势。\n",
    ]

    if synthesis:
        parts.append(synthesis)
        parts.append("")

    # 补充 high-confidence 数据点
    if findings:
        high_conf_points = []
        for _question, finding in findings.items():
            if finding.get("confidence") == "high":
                for dp in (finding.get("data_points") or [])[:2]:
                    high_conf_points.append(dp)

        if high_conf_points:
            parts.append("### 高置信度数据点\n")
            for dp in high_conf_points[:8]:
                source = dp.get("source", "")
                parts.append(f"- {dp.get('metric', '')}: {dp.get('value', '')} ({source})")
            parts.append("")

    return "\n".join(parts)


def format_research_for_big_idea(result_data: dict | None) -> str:
    """Big Idea 层（brand_strategy 第 3 层）：压缩要点

    Big Idea 层 token 预算紧张，只注入最核心的市场趋势要点，
    供创意锚定现实市场语境。
    """
    rd = _load_result(result_data)
    synthesis = rd.get("synthesis", "")
    findings = rd.get("findings_by_question")

    if not synthesis and not findings:
        return ""

    parts = [
        "## 市场趋势要点（Research Agent）\n",
    ]

    # 从 findings 中提取 high-confidence 答案的首句
    if findings:
        for question, finding in findings.items():
            if finding.get("confidence") in ("high", "medium"):
                summary = finding.get("answer_summary", "")
                # 取首句（句号或换行截断）
                first_sentence = summary.split("。")[0] + "。" if "。" in summary else summary[:100]
                parts.append(f"- {first_sentence}")
        parts.append("")

    return "\n".join(parts)


def format_research_for_agenda_map(result_data: dict | None) -> str:
    """Agenda Map 层（market_report 第 1 层）：完整研究发现

    与 Insight 类似，Agenda Map 是第 1 层，需要完整外部数据来交叉验证
    媒体叙事是否与行业实际趋势一致。
    """
    rd = _load_result(result_data)
    findings = rd.get("findings_by_question")
    gaps = rd.get("information_gaps")

    if not findings:
        return ""

    parts = [
        "## 行业研究发现（Research Agent）\n",
        "以下数据来自自动化行业研究，代表**专家/行业视角**，"
        "可用于校验媒体叙事是否与行业实际趋势一致——若出现偏差，即为值得标注的 attention_gap。\n",
        "### 研究发现\n",
    ]

    for question, finding in findings.items():
        confidence = finding.get("confidence", "medium")
        parts.append(f"**Q: {question}** (置信度: {confidence})")
        parts.append(f"  答：{finding.get('answer_summary', '')}")

        data_points = finding.get("data_points") or []
        if data_points:
            parts.append("  关键数据：")
            for dp in data_points[:5]:
                source = dp.get("source", "")
                period = dp.get("period", "")
                suffix = f" ({period}, {source})" if period and source else ""
                parts.append(f"  - {dp.get('metric', '')}: {dp.get('value', '')}{suffix}")
        parts.append("")

    if gaps:
        parts.append("### 信息缺口\n")
        for gap in gaps[:5]:
            parts.append(f"- {gap}")
        parts.append("")

    return "\n".join(parts)


def format_research_for_landscape(result_data: dict | None) -> str:
    """Landscape 层（market_report 第 2 层）：synthesis + 量化数据

    Landscape 需要行业背景来校验玩家定位和市场动态，
    synthesis 提供宏观视角，data_points 提供量化验证。
    """
    rd = _load_result(result_data)
    synthesis = rd.get("synthesis", "")
    findings = rd.get("findings_by_question")

    if not synthesis and not findings:
        return ""

    parts = [
        "## 行业研究背景（Research Agent）\n",
        "以下为行业研究综合分析，供竞争格局分析时校验市场份额、趋势判断。\n",
    ]

    if synthesis:
        parts.append(synthesis)
        parts.append("")

    # 提取所有数据点（量化数据对 Landscape 特别有价值）
    if findings:
        all_points = []
        for _question, finding in findings.items():
            for dp in (finding.get("data_points") or [])[:3]:
                all_points.append(dp)

        if all_points:
            parts.append("### 量化数据点\n")
            for dp in all_points[:10]:
                source = dp.get("source", "")
                period = dp.get("period", "")
                suffix = f" ({period}, {source})" if period and source else ""
                parts.append(f"- {dp.get('metric', '')}: {dp.get('value', '')}{suffix}")
            parts.append("")

    return "\n".join(parts)


def format_research_for_strategic_brief(result_data: dict | None) -> str:
    """Strategic Brief 层（market_report 第 3 层）：压缩证据锚点

    Strategic Brief 原则上"禁止引入新数据"，但研究发现作为已有背景（非新数据源）
    可以为 strategic_priorities 的 evidence 提供额外锚点。仅注入高置信度要点。
    """
    rd = _load_result(result_data)
    findings = rd.get("findings_by_question")

    if not findings:
        return ""

    high_conf = [
        (q, f) for q, f in findings.items()
        if f.get("confidence") == "high"
    ]

    if not high_conf:
        return ""

    parts = [
        "## 行业研究要点（Research Agent，仅高置信度）\n",
        "以下为已验证的行业事实，可作为战略优先级的证据锚点。\n",
    ]
    for question, finding in high_conf[:5]:
        summary = finding.get("answer_summary", "")
        first_sentence = summary.split("。")[0] + "。" if "。" in summary else summary[:100]
        parts.append(f"- **{question}**: {first_sentence}")

    parts.append("")
    return "\n".join(parts)
