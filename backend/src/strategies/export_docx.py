"""策略报告 Word 导出

生成 brand_strategy 路径 3 个递进层结果的 Word 文档
（insight → brand_role → big_idea）。
复用 analysis/export_docx 的样式设置和 Markdown 渲染。
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from src.social_media.analysis.export_docx import _setup_styles

from .models import Strategy


def generate_strategy_docx(strategy: Strategy) -> BytesIO:
    """从策略记录生成 Word 文档（多分支：仅导出 selected branch）"""
    doc = Document()
    _setup_styles(doc)

    # 封面
    _add_cover(doc, strategy)

    # 洞察层
    _add_insight_section(doc, strategy.insight_result)

    # 多分支：取 selected=true 的分支；无则按完成度回退（big_idea > brand_role > 第一个）
    selected = _pick_export_branch(strategy.brand_strategy_branches)
    branch_brand_role = (selected or {}).get("brand_role")
    branch_big_idea = (selected or {}).get("big_idea")
    branch_label = _format_branch_label(selected)

    # 品牌角色层
    _add_brand_role_section(doc, branch_brand_role, branch_label=branch_label)

    # 创意层
    _add_big_idea_section(doc, branch_big_idea, branch_label=branch_label)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _pick_export_branch(branches: list[dict] | None) -> dict | None:
    """选取要导出的分支：selected=true 优先；否则按完成度回退"""
    if not branches:
        return None
    selected = next(
        (b for b in branches if isinstance(b, dict) and b.get("selected")),
        None,
    )
    if selected:
        return selected
    with_big_idea = next(
        (b for b in branches if isinstance(b, dict) and b.get("big_idea")),
        None,
    )
    if with_big_idea:
        return with_big_idea
    with_brand_role = next(
        (b for b in branches if isinstance(b, dict) and b.get("brand_role")),
        None,
    )
    if with_brand_role:
        return with_brand_role
    return branches[0] if isinstance(branches[0], dict) else None


def _format_branch_label(branch: dict | None) -> str:
    """生成分支标题尾缀，如 "（基于 Tension 1：xxxx）"。"""
    if not branch:
        return ""
    tension_id = branch.get("tension_id")
    summary = (branch.get("tension_summary") or "").strip()
    if tension_id is None and not summary:
        return ""
    if summary:
        return f"（基于 Tension {int(tension_id) + 1 if isinstance(tension_id, int) else '?'}：{summary}）"
    return f"（基于 Tension {int(tension_id) + 1}）"


def _add_cover(doc: Document, strategy: Strategy) -> None:
    """封面页"""
    doc.add_paragraph("")
    doc.add_paragraph("")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(strategy.name)
    run.font.size = Pt(24)
    run.bold = True

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("策略报告")
    run.font.size = Pt(16)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p.add_run(f"生成日期: {date_str}")

    doc.add_page_break()


def _add_insight_section(doc: Document, insight: dict | None) -> None:
    """第 1 层 Insight (洞察): Social Tension + Brand Opportunity"""
    doc.add_heading("第 1 层 Insight: 洞察", level=1)

    if not insight:
        doc.add_paragraph("（未完成）")
        return

    # Social Tensions
    tensions = insight.get("social_tensions", [])
    if tensions:
        doc.add_heading("Social Tension", level=2)
        for i, t in enumerate(tensions):
            statement = t.get("statement", "")
            confidence = t.get("confidence", "")
            doc.add_heading(f"Tension {i + 1}: {statement}", level=3)
            if confidence:
                doc.add_paragraph(f"置信度: {confidence}")
            _add_evidence_list(doc, t.get("evidence", []))

    # Brand Opportunities
    opportunities = insight.get("brand_opportunities", [])
    if opportunities:
        doc.add_heading("Brand Opportunity", level=2)
        for i, o in enumerate(opportunities):
            statement = o.get("statement", "")
            doc.add_heading(f"Opportunity {i + 1}: {statement}", level=3)
            related = o.get("related_tensions", [])
            if related:
                doc.add_paragraph(f"关联 Tension: {related}")
            _add_evidence_list(doc, o.get("evidence", []))


def _add_brand_role_section(
    doc: Document,
    brand_role: dict | None,
    *,
    branch_label: str = "",
) -> None:
    """第 2 层 Brand Role (品牌角色): Brand Social Role + Social Strategy"""
    doc.add_heading(f"第 2 层 Brand Role: 品牌角色{branch_label}", level=1)

    if not brand_role:
        doc.add_paragraph("（未完成）")
        return

    # Brand Social Role
    role = brand_role.get("brand_social_role", {})
    if role:
        doc.add_heading("Brand Social Role", level=2)
        if role.get("statement"):
            p = doc.add_paragraph()
            run = p.add_run(role["statement"])
            run.bold = True
            run.font.size = Pt(12)
        if role.get("elaboration"):
            doc.add_paragraph(role["elaboration"])
        _add_evidence_list(doc, role.get("evidence", []))

    # Social Strategy
    social_strategy = brand_role.get("social_strategy", {})
    if social_strategy:
        doc.add_heading("Social Strategy", level=2)
        if social_strategy.get("statement"):
            p = doc.add_paragraph()
            run = p.add_run(social_strategy["statement"])
            run.bold = True
            run.font.size = Pt(12)
        if social_strategy.get("core_message"):
            doc.add_paragraph(f"核心信息: {social_strategy['core_message']}")
        if social_strategy.get("rhythm"):
            doc.add_paragraph(f"传播节奏: {social_strategy['rhythm']}")
        _add_evidence_list(doc, social_strategy.get("evidence", []))


def _add_big_idea_section(
    doc: Document,
    big_idea: dict | None,
    *,
    branch_label: str = "",
) -> None:
    """第 3 层 Big Idea (创意): Big Idea + Content Strategy"""
    doc.add_heading(f"第 3 层 Big Idea: 创意{branch_label}", level=1)

    if not big_idea:
        doc.add_paragraph("（未完成）")
        return

    # Big Idea
    idea = big_idea.get("big_idea", {})
    if idea:
        doc.add_heading("Big Idea", level=2)
        if idea.get("statement"):
            p = doc.add_paragraph()
            run = p.add_run(idea["statement"])
            run.bold = True
            run.font.size = Pt(14)
        if idea.get("elaboration"):
            doc.add_paragraph(idea["elaboration"])
        if idea.get("tension_echo"):
            doc.add_paragraph(f"与核心矛盾的呼应: {idea['tension_echo']}")
        _add_evidence_list(doc, idea.get("evidence", []))

    # Content Strategy
    content = big_idea.get("content_strategy", {})
    if content:
        doc.add_heading("Content Strategy", level=2)
        pillars = content.get("pillars", [])
        for i, pillar in enumerate(pillars):
            doc.add_heading(f"支柱 {i + 1}: {pillar.get('name', '')}", level=3)
            if pillar.get("description"):
                doc.add_paragraph(pillar["description"])
            examples = pillar.get("reference_examples", [])
            if examples:
                doc.add_paragraph("参考案例:")
                for ex in examples:
                    doc.add_paragraph(f"  - {ex}", style="List Bullet")
        _add_evidence_list(doc, content.get("evidence", []))


def _add_evidence_list(doc: Document, evidence: list[dict]) -> None:
    """添加论据列表"""
    if not evidence:
        return
    doc.add_paragraph("")
    doc.add_paragraph("数据论据:", style="Normal")
    for e in evidence:
        desc = e.get("description", "")
        etype = e.get("type", "")
        source = e.get("source", "")
        text = f"[{etype}] {desc}"
        if source:
            text += f" (来源: {source})"
        doc.add_paragraph(text, style="List Bullet")
