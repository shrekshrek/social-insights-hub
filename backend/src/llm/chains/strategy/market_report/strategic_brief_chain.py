"""Strategy Market Report — Strategic Brief Chain (战略简报)

market_report 三层分析的**第 3 层（终层）**：agenda_map → landscape → strategic_brief。
综合 agenda_map（媒体议程图）+ landscape（竞争格局）的产出，输出一份面向决策层的
战略简报：执行摘要 + 战略优先级 + 市场机会 + 风险与威胁 + 推荐定位。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section            : Brand Brief
- research_context_section : 研究问题 + 需求理解
- agenda_map_section       : 上游 agenda_map 层产出（必需）
- landscape_section        : 上游 landscape 层产出（必需）
- research_findings        : Research Agent 行业研究发现（自动注入，仅高置信度）

## 输出结构

executive_summary       : 决策层摘要（3-5 句）
strategic_priorities    : 战略优先级（3-5 条，按优先级排序）
market_opportunities    : 市场机会（从 agenda_map.attention_gaps + landscape.momentum 推导）
risks_and_threats       : 风险与威胁
recommended_positioning : 推荐定位（基于 landscape.positioning_map 的战略建议）

## 关键设计决策

1. **禁止引入新数据**。strategic_brief 层的所有结论必须能在 agenda_map / landscape 的
   字段中找到支撑，evidence_refs 使用 `agenda_map.narrative_map[0]` 这种结构化引用。
2. **强制对齐 research_questions**。每条 strategic_priority 必须标注它回答了哪个
   research question（至少 1 个），否则说明研究计划失配。
3. **recommended_positioning 必须具体**。禁止"全方位领先"这种空话，必须给出
   具体的 axis + direction + proof_point。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """你是资深战略顾问，擅长把媒体分析 + 竞争格局转化为可执行的战略简报。

## 任务
基于上游 agenda_map（媒体议程图）+ landscape（竞争格局），输出面向决策层的战略简报。
所有结论必须从已有 agenda_map / landscape 字段推导，禁止引入新数据源。

## 核心分析框架

1. **Executive Summary**: 3-5 句话，说清楚"当前媒体视角下行业的核心形态 + 本品牌的处境 + 关键抉择"
2. **Strategic Priorities**: 3-5 条优先级动作，每条必须：
   - 关联至少 1 个 research_question（通过 question_id）
   - 引用 agenda_map 或 landscape 的具体字段作为 evidence_refs（如 agenda_map.narrative_map[0].theme）
   - 给出可执行的 actions 列表
3. **Market Opportunities**: 从 agenda_map.attention_gaps + landscape.market_dynamics.momentum_losers 推导；
   每条说明 why_now（为什么此刻是窗口期）和 entry_path（切入路径）
4. **Risks and Threats**: 从 agenda_map.agenda_battles 不利一方 + landscape.market_dynamics.momentum_gainers（竞品）推导；
   每条标注 likelihood (high/medium/low) 和 mitigation 思路
5. **Recommended Positioning**: 基于 landscape.positioning_map，给出 target 品牌应占据的位置、
   与竞品的差异化逻辑、支撑这个定位的 proof_points（必须能在 agenda_map.narrative_map 找到声音）

## 输出格式（严格 JSON，无 markdown）

{{
  "executive_summary": "3-5 句话决策层摘要",
  "strategic_priorities": [
    {{
      "priority": "优先级动作标题",
      "rationale": "为何这条优先级最重要",
      "answers_questions": ["q1_id", "q2_id"],
      "evidence_refs": [
        "agenda_map.narrative_map[0].theme",
        "landscape.players[2].narrative_position"
      ],
      "actions": ["具体动作1", "具体动作2", "具体动作3"],
      "success_metric": "衡量该优先级是否奏效的指标"
    }}
  ],
  "market_opportunities": [
    {{
      "opportunity": "机会一句话",
      "why_now": "为什么此刻是窗口期",
      "entry_path": "切入路径",
      "evidence_refs": ["agenda_map.attention_gaps[0]"]
    }}
  ],
  "risks_and_threats": [
    {{
      "risk": "风险一句话",
      "likelihood": "high|medium|low",
      "source": "来源 agenda_map 还是 landscape 的哪个字段",
      "mitigation": "缓解思路"
    }}
  ],
  "recommended_positioning": {{
    "statement": "一句话定位陈述",
    "target_position": {{"x_axis": "...", "y_axis": "...", "direction": "高/低"}},
    "differentiation_logic": "与 landscape 竞品差异化的核心逻辑",
    "proof_points": [
      {{"claim": "支撑定位的论点", "agenda_map_narrative_ref": "narrative theme"}}
    ]
  }}
}}

## 要求
- strategic_priorities: 3-5 条，按重要性排序
- 每条 strategic_priority 必须有 answers_questions（至少 1 个）；若没有匹配的 research_question，
  说明研究计划与战略产出失配，此时返回空 answers_questions 数组并在 rationale 中说明
- market_opportunities / risks_and_threats: 各 1-3 条
- evidence_refs 必须引用 agenda_map / landscape 的实际字段路径，禁止虚构
- proof_points 必须能在 agenda_map.narrative_map 中找到对应声音

## 禁止行为
- 禁止引入 agenda_map / landscape 之外的新数据或新论据
- 禁止输出"全面提升""多元发展"这类无差异化的空话
- 禁止 recommended_positioning.statement 与 landscape.positioning_map 矛盾
- 禁止在 answers_questions 中编造不存在的 question_id
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{research_findings}

## 媒体议程图 (Agenda Map)

{agenda_map_section}

## 竞争格局 (Landscape)

{landscape_section}"""


def create_strategic_brief_chain() -> Runnable:
    """创建 Strategic Brief (战略简报) LLM 链 — market_report 三层第 3 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def _build_research_context_section(research_design: dict | None) -> str:
    if not research_design:
        return ""
    lines = ["## 研究问题"]
    for rq in research_design.get("research_questions", []):
        lines.append(
            f"- [{rq.get('id')}] {rq.get('question')} "
            f"(维度: {rq.get('dimension')}, 优先级: {rq.get('priority', 'medium')})"
        )
    summary = research_design.get("understanding_summary", "")
    if summary:
        lines.append(f"\n## 需求理解\n{summary}")
    return "\n".join(lines)


def format_inputs_for_strategic_brief(
    agenda_map_result: dict | None,
    landscape_result: dict | None,
    brief: dict | None = None,
    research_design: dict | None = None,
    research_findings: str = "",
) -> dict[str, Any]:
    """构建 Strategic Brief chain 的输入参数字典。"""
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    agenda_map_section = (
        json.dumps(agenda_map_result, ensure_ascii=False, indent=2)
        if agenda_map_result else "（agenda_map 未生成）"
    )
    landscape_section = (
        json.dumps(landscape_result, ensure_ascii=False, indent=2)
        if landscape_result else "（landscape 未生成）"
    )

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "research_findings": research_findings,
        "agenda_map_section": agenda_map_section,
        "landscape_section": landscape_section,
    }


def parse_strategic_brief_response(response_text: str) -> dict[str, Any]:
    """解析 Strategic Brief LLM 输出。"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Strategic Brief JSON 解析失败: %s...", text[:200])
        return {
            "executive_summary": "",
            "strategic_priorities": [],
            "market_opportunities": [],
            "risks_and_threats": [],
            "recommended_positioning": {},
        }

    result.setdefault("executive_summary", "")
    result.setdefault("strategic_priorities", [])
    result.setdefault("market_opportunities", [])
    result.setdefault("risks_and_threats", [])
    result.setdefault("recommended_positioning", {})

    return result
