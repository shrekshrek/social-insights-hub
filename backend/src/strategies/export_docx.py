"""策略报告 Word 导出

生成包含 3 个阶段结果的 Word 文档。
复用 analysis/export_docx 的样式设置和 Markdown 渲染。
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from src.analysis.export_docx import _setup_styles

from .models import Strategy


def generate_strategy_docx(strategy: Strategy) -> BytesIO:
    """从策略记录生成 Word 文档"""
    doc = Document()
    _setup_styles(doc)

    # 封面
    _add_cover(doc, strategy)

    # Phase 1
    _add_phase1_section(doc, strategy.phase1_result)

    # Phase 2
    _add_phase2_section(doc, strategy.phase2_result)

    # Phase 3
    _add_phase3_section(doc, strategy.phase3_result)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


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


def _add_phase1_section(doc: Document, phase1: dict | None) -> None:
    """Phase 1: Social Tension + Brand Opportunity"""
    doc.add_heading("Phase 1: 洞察层", level=1)

    if not phase1:
        doc.add_paragraph("（未完成）")
        return

    # Social Tensions
    tensions = phase1.get("social_tensions", [])
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
    opportunities = phase1.get("brand_opportunities", [])
    if opportunities:
        doc.add_heading("Brand Opportunity", level=2)
        for i, o in enumerate(opportunities):
            statement = o.get("statement", "")
            doc.add_heading(f"Opportunity {i + 1}: {statement}", level=3)
            related = o.get("related_tensions", [])
            if related:
                doc.add_paragraph(f"关联 Tension: {related}")
            _add_evidence_list(doc, o.get("evidence", []))


def _add_phase2_section(doc: Document, phase2: dict | None) -> None:
    """Phase 2: Brand Social Role + Social Strategy"""
    doc.add_heading("Phase 2: 策略层", level=1)

    if not phase2:
        doc.add_paragraph("（未完成）")
        return

    # Brand Social Role
    role = phase2.get("brand_social_role", {})
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
    strategy = phase2.get("social_strategy", {})
    if strategy:
        doc.add_heading("Social Strategy", level=2)
        if strategy.get("statement"):
            p = doc.add_paragraph()
            run = p.add_run(strategy["statement"])
            run.bold = True
            run.font.size = Pt(12)
        if strategy.get("core_message"):
            doc.add_paragraph(f"核心信息: {strategy['core_message']}")
        if strategy.get("rhythm"):
            doc.add_paragraph(f"传播节奏: {strategy['rhythm']}")
        _add_evidence_list(doc, strategy.get("evidence", []))


def _add_phase3_section(doc: Document, phase3: dict | None) -> None:
    """Phase 3: Big Idea + Content Strategy"""
    doc.add_heading("Phase 3: 创意层", level=1)

    if not phase3:
        doc.add_paragraph("（未完成）")
        return

    # Big Idea
    idea = phase3.get("big_idea", {})
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
    content = phase3.get("content_strategy", {})
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
