"""Strategy Market Report — Strategic Brief Chain (战略简报)

**双模式终层 chain**：

- **media_only 模式**（market_report 路径）：综合 agenda_map + landscape 输出
  纯媒体战略简报，服务 PR/comms 团队。
- **comprehensive 模式**（full_strategy 路径）：除媒体侧外，**同时综合**
  Insight（消费者矛盾）+ Brand Strategy Branches（多分支 brand_role + big_idea）+
  creative_references，输出 CMO 级综合战略简报。并结合 landscape.players 的消费者侧字段
  （consumer_standing / consumer_organic_sentiment，full_strategy 才有值）做逐竞品的客观竞争判断。

模式自动判定：根据 USER_TEMPLATE 中 `{insight_section}` /
`{brand_strategy_branches_section}` 是否为空切换。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section                    : Brand Brief（必须作为品牌视角过滤器，驱动取舍判断）
- research_context_section         : 研究问题 + 需求理解
- coverage_signals                 : 跨切片数据质量诊断（warnings + data_highlights）
- agenda_map_section               : 上游 agenda_map 层产出（必需）
- landscape_section                : 上游 landscape 层产出（必需）
- insight_section                  : 消费者洞察层产出；comprehensive 模式注入，media_only 为空
- brand_strategy_branches_section  : 多分支 brand_role + big_idea 输出；comprehensive 模式注入
- research_findings                : Research Agent 行业研究发现
- creative_references              : 创意研究（数英 / SocialBeta），comprehensive 模式可选

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
   "新市场事实" = 上游各层里没有出现过的市场数据或论断（禁止）。
   "品牌约束判断" = 基于 brand_brief 对已有信息做优先级排序（必须）。

3. **recommended_positioning 必须论证"为什么是这个品牌"**。
   why_this_brand_can_own_it 字段要求说明：该品牌凭什么能占据这个定位，
   竞品（已出现在 landscape.players）为何无法跟进或难以复制。

4. **强制对齐 research_questions**。每条 strategic_priority 必须标注它回答了哪个
   research question（至少 1 个），否则说明研究计划与战略产出失配。

5. **comprehensive 模式下 evidence_refs 跨层引用**。
   - media_only：仅允许 ref `agenda_map.*` / `landscape.*` 字段
   - comprehensive：**额外允许** ref `insight.social_tensions[X]` /
     `insight.brand_opportunities[X]` / `brand_strategy_branches[X].brand_role` /
     `brand_strategy_branches[X].big_idea`，必须把消费者洞察纳入 priority 推导
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.chains.strategy.research_findings import format_coverage_signals
from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """你是资深战略顾问，擅长把市场分析转化为品牌专属的可执行战略简报。

## 任务
基于上游产出（媒体议程图 + 竞争格局，**comprehensive 模式下还含消费者洞察 + 品牌策略多分支**），
以 brand_brief 为过滤器，输出这个品牌专属的战略简报。

**核心价值主张**：上游各层描述市场/消费者全貌，但所有品牌看到的是同一份数据。
Strategic Brief 的独特价值在于：用 brand_brief（分析目标、所处赛道、constraints）
过滤、做出该品牌而非通用的取舍判断——哪些机会这个品牌能拿，哪些拿不到，为什么。

## 模式判定

USER_TEMPLATE 中如果 `## 消费者洞察 (Insight)` 段落非空 = **comprehensive 模式**：
- 必须把消费者矛盾（social_tensions）纳入 priority 推导逻辑
- 必须考察 brand_strategy_branches 中**已 selected 的分支**（或多个 brand_role/big_idea），
  把品牌的 social role 与战略推荐 statement 整合到 recommended_positioning
- evidence_refs 跨层引用消费者侧字段

否则 = **media_only 模式**：
- 只基于 agenda_map + landscape 推导，输出聚焦媒体战略 / PR 焦点
- evidence_refs 只引用 agenda_map / landscape

## 分析步骤

**第一步：定位品牌当前处境**
从 landscape.players 找到 target 品牌的 media_sov_pct / media_sentiment / narrative_position，
结合 brand_brief.analysis_goal，判断品牌目前是"防守""追击"还是"领跑"状态。
**comprehensive 模式**：
- 考察 insight.social_tensions——消费者侧是否有未解矛盾正在影响品牌处境。
- **并读 landscape.players 的消费者侧字段**（`consumer_standing` / `consumer_organic_sentiment`，仅 full_strategy 有）：
  这是逐竞品的消费者侧真实地位（基于社媒 organic 数据）。media_sov 是媒体声量、organic 是消费者声量，口径不同；
  把两侧结合**客观**判断各玩家处境，**结论由数据得出，不预设**。
  （与 insight.social_tensions 互补：landscape 消费者字段给**逐竞品**地位，insight 给**主品**消费者张力。）

**第二步：品牌视角过滤机会**
Agenda Map 的 attention_gaps + insight.brand_opportunities（如有）共同构成机会池。
逐条评估：
- 该品牌的分析目标（brand_brief.analysis_goal）与这个机会的方向是否一致？
- 该品牌在 landscape.positioning_map 上的当前位置，能否可信地切入？
- landscape.players 中的竞品是否已在抢占？品牌的差异化空间在哪里？
- **comprehensive 模式**：brand_strategy_branches 中已 selected 的分支 brand_role 是否与该机会方向一致？
筛选后留下 brand_fit=high 的优先推进，brand_fit=low 的标注原因后降优先级。

**第三步：推导品牌专属定位**
从 landscape.positioning_map 出发，找到 target 品牌当前位置。
**comprehensive 模式**：整合 brand_strategy_branches 中 selected 分支的 brand_social_role.statement +
big_idea.statement，让推荐定位与品牌策略层、创意层一致——而非只基于媒体定位。
论证"为什么是这个品牌能做到"：竞品为何难以跟进（叙事基础、media_sentiment 制约等）？

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
        "landscape.players[2].narrative_position",
        "insight.social_tensions[1] (仅 comprehensive 模式)",
        "brand_strategy_branches[0].brand_role.brand_social_role.statement (仅 comprehensive 模式)"
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
- risks_and_threats: 1-3 条。comprehensive 模式下，landscape.players 的 consumer_standing /
  consumer_organic_sentiment 与媒体侧若有差异，可据此客观补充风险/威胁——由数据得出，不预设、不臆造。
- evidence_refs 必须引用 agenda_map / landscape 的实际字段路径，禁止虚构（landscape 的消费者侧字段
  如 `landscape.players[X].consumer_standing` / `consumer_organic_sentiment` 也是合法 ref，仅 comprehensive 模式有值）

## 禁止行为
- 禁止引入 agenda_map / landscape 之外的新市场数据（market facts）
- 禁止输出对所有品牌都成立的通用建议——每条结论都应说明"为什么是这个品牌"
- 禁止 recommended_positioning.statement 与 landscape.positioning_map 矛盾
- 禁止在 answers_questions 中编造不存在的 question_id
- 禁止输出"全面提升""多元发展"这类无差异化的空话
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{coverage_signals}

{research_findings}

{creative_references}

## 媒体议程图 (Agenda Map)

{agenda_map_section}

## 竞争格局 (Landscape)

{landscape_section}

{insight_section}

{brand_strategy_branches_section}"""


def create_strategic_brief_chain() -> Runnable:
    """创建 Strategic Brief (战略简报) LLM 链 — market_report 三层第 3 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            ("user", USER_TEMPLATE),
        ]
    )
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


def _format_insight_section(insight_result: dict | None) -> str:
    """comprehensive 模式下注入消费者洞察层产出（去掉 evidence 减少 token）"""
    if not insight_result:
        return ""
    tensions = insight_result.get("social_tensions") or []
    opportunities = insight_result.get("brand_opportunities") or []
    slim = {
        "social_tensions": [
            {
                "id": idx,
                "statement": t.get("statement"),
                "conventional_wisdom": t.get("conventional_wisdom"),
                "data_reality": t.get("data_reality"),
                "confidence": t.get("confidence"),
                "research_questions_addressed": t.get("research_questions_addressed"),
            }
            for idx, t in enumerate(tensions)
            if isinstance(t, dict)
        ],
        "brand_opportunities": [
            {
                "id": idx,
                "statement": o.get("statement"),
                "why_non_obvious": o.get("why_non_obvious"),
                "related_tensions": o.get("related_tensions"),
                "research_questions_addressed": o.get("research_questions_addressed"),
            }
            for idx, o in enumerate(opportunities)
            if isinstance(o, dict)
        ],
    }
    return "## 消费者洞察 (Insight)\n\n" + json.dumps(
        slim, ensure_ascii=False, indent=2
    )


def _format_brand_strategy_branches_section(
    branches: list[dict] | None,
) -> str:
    """comprehensive 模式下注入多分支 brand_role + big_idea 输出。

    精简：仅保留 statement 级核心字段（剔除 evidence / data_provenance），
    优先标注 selected 分支让 LLM 重点参考。
    """
    if not branches:
        return ""
    slim_branches = []
    for b in branches:
        if not isinstance(b, dict):
            continue
        brand_role = b.get("brand_role") or {}
        big_idea = b.get("big_idea") or {}
        slim = {
            "tension_id": b.get("tension_id"),
            "tension_summary": b.get("tension_summary"),
            "selected": b.get("selected", False),
            "status": b.get("status"),
        }
        if brand_role:
            br_role = brand_role.get("brand_social_role") or {}
            br_strategy = brand_role.get("social_strategy") or {}
            slim["brand_role"] = {
                "brand_social_role_statement": br_role.get("statement"),
                "social_strategy_statement": br_strategy.get("statement"),
                "core_message": br_strategy.get("core_message"),
            }
        if big_idea:
            bi = big_idea.get("big_idea") or {}
            content = big_idea.get("content_strategy") or {}
            slim["big_idea"] = {
                "big_idea_statement": bi.get("statement"),
                "tension_echo": bi.get("tension_echo"),
                "content_pillars": [
                    p.get("name")
                    for p in (content.get("pillars") or [])
                    if isinstance(p, dict) and p.get("name")
                ],
            }
        slim_branches.append(slim)

    return (
        "## 品牌策略多分支 (Brand Strategy Branches)\n\n"
        "**注意**：标记 `selected: true` 的分支是用户选定的主推方向，"
        "推导 recommended_positioning 时应优先整合该分支的 brand_role + big_idea。\n\n"
        + json.dumps(slim_branches, ensure_ascii=False, indent=2)
    )


def format_inputs_for_strategic_brief(
    agenda_map_result: dict | None,
    landscape_result: dict | None,
    brief: dict | None = None,
    research_design: dict | None = None,
    research_findings: str = "",
    coverage_check_result: dict | None = None,
    insight_result: dict | None = None,
    brand_strategy_branches: list[dict] | None = None,
    creative_references: str = "",
) -> dict[str, Any]:
    """构建 Strategic Brief chain 的输入参数字典。

    media_only 模式（market_report 路径）：insight_result / brand_strategy_branches /
    creative_references 留空，输出聚焦媒体战略简报。

    comprehensive 模式（full_strategy 路径）：注入消费者侧 + 多分支 + 创意研究，
    输出综合战略简报；prompt 自动检测 insight_section 段落非空切换分析逻辑。
    """
    brief_section = ""
    if brief:
        brief_section = (
            f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        )

    agenda_map_section = (
        json.dumps(agenda_map_result, ensure_ascii=False, indent=2)
        if agenda_map_result
        else "（agenda_map 未生成）"
    )
    landscape_section = (
        json.dumps(landscape_result, ensure_ascii=False, indent=2)
        if landscape_result
        else "（landscape 未生成）"
    )

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "coverage_signals": format_coverage_signals(coverage_check_result),
        "research_findings": research_findings,
        "creative_references": creative_references,
        "agenda_map_section": agenda_map_section,
        "landscape_section": landscape_section,
        "insight_section": _format_insight_section(insight_result),
        "brand_strategy_branches_section": _format_brand_strategy_branches_section(
            brand_strategy_branches
        ),
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
