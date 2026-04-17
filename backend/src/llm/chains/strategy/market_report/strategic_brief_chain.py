"""Strategy Market Report — Strategic Brief Chain (战略简报)

market_report 三层分析的**第 3 层（终层）**：agenda_map → landscape → strategic_brief。
综合 agenda_map（媒体议程图）+ landscape（竞争格局）的产出，**以 brand_brief 为过滤器**，
输出一份面向决策层的战略简报：执行摘要 + 战略优先级 + 市场机会 + 风险与威胁 + 推荐定位。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section            : Brand Brief（必须作为品牌视角过滤器，驱动取舍判断）
- research_context_section : 研究问题 + 需求理解
- agenda_map_section       : 上游 agenda_map 层产出（必需）
- landscape_section        : 上游 landscape 层产出（必需）
- research_findings        : Research Agent 行业研究发现（自动注入，仅高置信度）

## 输出结构

executive_summary       : 决策层摘要（3-5 句，含品牌当前处境判断）
strategic_priorities    : 战略优先级（3-5 条，按品牌可行性+机会价值双维排序）
market_opportunities    : 市场机会（含 brand_fit 品牌匹配度评估）
risks_and_threats       : 风险与威胁
recommended_positioning : 推荐定位（含 why_this_brand_can_own_it 可行性论证）

## 关键设计决策

1. **brand_brief 是取舍过滤器，而非背景板**。
   Agenda Map 和 Landscape 描述的是市场全貌，Strategic Brief 的核心价值在于：
   用 brand_brief（分析目标、所处赛道、constraints）过滤市场机会，回答
   "这个品牌具体该做什么"——而非对所有品牌都成立的通用建议。
   market_opportunities 中的 brand_fit 字段强制要求 LLM 评估每个机会与该品牌的匹配程度。

2. **禁止引入新的市场事实**，但必须基于 brand_brief 约束做取舍判断。
   "新市场事实" = Agenda Map / Landscape 里没有出现过的市场数据或论断（禁止）。
   "品牌约束判断" = 基于 brand_brief.analysis_goal / constraints 对已有机会做优先级排序（必须）。
   两者性质不同，不要混为一谈。

3. **recommended_positioning 必须论证"为什么是这个品牌"**。
   why_this_brand_can_own_it 字段要求说明：该品牌凭什么能占据这个定位，
   竞品（已出现在 landscape.players）为何无法跟进或难以复制。
   禁止输出对所有玩家都成立的定位建议。

4. **强制对齐 research_questions**。每条 strategic_priority 必须标注它回答了哪个
   research question（至少 1 个），否则说明研究计划与战略产出失配。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """你是资深战略顾问，擅长把媒体分析 + 竞争格局转化为品牌专属的可执行战略简报。

## 任务
基于上游 agenda_map（媒体议程图）+ landscape（竞争格局），以 brand_brief 为过滤器，
输出这个品牌专属的战略简报。

**核心价值主张**：Agenda Map 和 Landscape 描述市场全貌，但所有品牌看到的是同一份数据。
Strategic Brief 的独特价值在于：用 brand_brief（分析目标、所处赛道、constraints）
过滤市场机会，做出该品牌而非通用的取舍判断——哪些机会这个品牌能拿，哪些拿不到，为什么。

## 分析步骤

**第一步：定位品牌当前处境**
从 landscape.players 找到 target 品牌的 media_sov_pct / media_sentiment / narrative_position，
结合 brand_brief.analysis_goal，判断品牌目前是"防守""追击"还是"领跑"状态。
这个判断将贯穿后续所有优先级决策。

**第二步：品牌视角过滤机会**
Agenda Map 的 attention_gaps 列出了市场中所有值得报道却缺位的议题。
但不是每个 gap 都适合这个品牌去占领。逐条评估：
- 该品牌的分析目标（brand_brief.analysis_goal）与这个 gap 的方向是否一致？
- 该品牌在 landscape.positioning_map 上的当前位置，能否可信地切入这个 gap？
- landscape.players 中的竞品是否已在抢占这个 gap？品牌的差异化空间在哪里？
筛选后留下 brand_fit=high 的机会优先推进，brand_fit=low 的机会标注原因后降优先级。

**第三步：推导品牌专属定位**
从 landscape.positioning_map 出发，找到 target 品牌当前位置，
推断它应该向哪个方向移动——但必须论证"为什么是这个品牌能做到"：
该品牌在 landscape.players 中的 key_claims / narrative_position 是否支撑这个方向？
竞品为何难以跟进（已占据其他位置、缺乏相关叙事、media_sentiment 制约等）？

## 输出格式（严格 JSON，无 markdown）

{{
  "executive_summary": "3-5 句话：当前媒体视角下行业核心形态 + 本品牌在 landscape 中的实际处境（防守/追击/领跑）+ 最关键的一个抉择",
  "strategic_priorities": [
    {{
      "priority": "优先级动作标题",
      "rationale": "为何这条对该品牌最重要（结合品牌当前处境，而非通用逻辑）",
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
      "brand_fit": "high|medium|low",
      "brand_fit_rationale": "为何该机会与品牌 brief 的目标/赛道匹配或不匹配",
      "why_now": "为什么此刻是窗口期（结合 landscape 的竞争态势）",
      "entry_path": "该品牌切入的具体路径（区别于竞品的切入方式）",
      "evidence_refs": ["agenda_map.attention_gaps[0]"]
    }}
  ],
  "risks_and_threats": [
    {{
      "risk": "风险一句话",
      "likelihood": "high|medium|low",
      "source": "来源 agenda_map / landscape 哪个字段",
      "mitigation": "该品牌具体的缓解思路（考虑品牌当前处境）"
    }}
  ],
  "recommended_positioning": {{
    "statement": "一句话定位陈述",
    "target_position": {{"x_axis": "...", "y_axis": "...", "direction": "高/低"}},
    "differentiation_logic": "与 landscape 竞品差异化的核心逻辑",
    "why_this_brand_can_own_it": "该品牌凭什么能占据这个定位——现有叙事基础 / 竞品为何难以跟进",
    "proof_points": [
      {{"claim": "支撑定位的论点", "agenda_map_narrative_ref": "narrative theme"}}
    ]
  }}
}}

## 要求
- strategic_priorities: 3-5 条，按"品牌可行性 × 机会价值"双维排序，而非单纯按机会价值
- 每条 strategic_priority 必须有 answers_questions（至少 1 个）；若没有匹配项，
  返回空数组并在 rationale 中说明研究计划与战略产出的失配
- market_opportunities: 1-3 条，brand_fit=low 的机会也可列出，但须说明为何当前不适合切入
- risks_and_threats: 1-3 条
- evidence_refs 必须引用 agenda_map / landscape 的实际字段路径，禁止虚构

## 禁止行为
- 禁止引入 agenda_map / landscape 之外的新市场数据（market facts）
- 禁止输出对所有品牌都成立的通用建议——每条结论都应说明"为什么是这个品牌"
- 禁止 recommended_positioning.statement 与 landscape.positioning_map 矛盾
- 禁止在 answers_questions 中编造不存在的 question_id
- 禁止输出"全面提升""多元发展"这类无差异化的空话
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
