"""Strategy Phase 1 Chain — 洞察层: Social Tension + Brand Opportunity

从切片数据中提取社会矛盾/未满足需求，及品牌可切入的机会。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位资深社交媒体策略分析师，擅长从数据中挖掘深层洞察。

## 任务
基于提供的切片分析数据，完成以下两项工作：
1. **Social Tension（社会矛盾）**：识别消费者在该品类/话题上的核心矛盾、痛点或未被满足的需求。
2. **Brand Opportunity（品牌机会）**：基于 Tension 和竞品空白区，找到品牌可以切入的差异化机会。

## 分析框架
- Social Tension 应来自用户真实观点、情感分布、争议话题
- Brand Opportunity 应结合竞品格局（SOV、四象限）找到空白区
- 每条结论必须附带数据论据（evidence），标明来源

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "social_tensions": [
    {{
      "statement": "一句话描述该矛盾",
      "evidence": [
        {{"type": "topic_sentiment", "description": "具体数据发现", "source": "slice数据"}},
        {{"type": "opinion_cluster", "description": "具体数据发现", "source": "slice数据"}}
      ],
      "confidence": "high/medium/low"
    }}
  ],
  "brand_opportunities": [
    {{
      "statement": "一句话描述品牌机会",
      "evidence": [
        {{"type": "sov_gap", "description": "具体数据发现", "source": "slice数据"}}
      ],
      "related_tensions": [0]
    }}
  ]
}}

## 要求
- social_tensions: 1-3 条，按重要性排序
- brand_opportunities: 1-2 条，每条引用相关 tension 的索引
- evidence 至少 2 条，类型可选: topic_sentiment, opinion_cluster, sov_gap, quadrant_position, kol_voice, time_trend, unmet_need
- confidence: high(数据充分)/medium(有支撑但需验证)/low(推测性)
"""

USER_TEMPLATE = """{brief_section}

{consult_summary}

{evaluation_summary}

## 切片数据

{slice_data}"""


def create_strategy_phase1_chain() -> Runnable:
    """创建 Phase 1 (洞察层) LLM 链"""
    llm = get_llm(llm_type="reasoner")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_slice_data_for_phase1(
    slices: list[dict],
    brief: dict | None = None,
    consultation_rounds: list[dict] | None = None,
    evaluation_result: dict | None = None,
) -> dict[str, Any]:
    """将切片 result_data 格式化为 Phase 1 输入

    从每个切片提取关键维度，严格控制总输入 ~30K tokens。
    结构化数据优先，按 Tension/Opportunity 两个产出目标精选字段。
    """
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    # 咨询摘要：取最新一轮的需求理解 + 切片规划
    consult_summary = ""
    if consultation_rounds:
        latest = consultation_rounds[-1]
        ai_resp = latest.get("ai_response") or {}
        lines = ["## AI 咨询摘要"]
        if ai_resp.get("understanding_summary"):
            lines.append(f"需求理解：{ai_resp['understanding_summary']}")
        slice_plan = ai_resp.get("slice_plan") or []
        if slice_plan:
            lines.append("预期分析切片：")
            for item in slice_plan:
                lines.append(f"- {item.get('name', '')}：{item.get('purpose', '')}")
        consult_summary = "\n".join(lines)

    # 评估摘要：数据缺口提示 LLM 注意数据局限性
    evaluation_summary = ""
    if evaluation_result:
        score = evaluation_result.get("overall_score", 0)
        is_sufficient = evaluation_result.get("is_sufficient", False)
        lines = [
            f"## 数据充分性评估（评分 {score:.0%}，{'数据充分' if is_sufficient else '数据待补充'}）"
        ]
        for gap in (evaluation_result.get("gap_analysis") or []):
            priority = gap.get("priority", "")
            desc = gap.get("description", "")
            lines.append(f"- 数据缺口（{priority}优先级）：{desc}")
        evaluation_summary = "\n".join(lines)

    slice_parts = []
    for i, s in enumerate(slices):
        meta = s.get("meta") or {}
        foundation = s.get("foundation") or {}
        layers = s.get("layers") or {}

        # 实体 top 10（精简字段 + issues 用于 Opportunity 推导竞品弱点）
        entities = foundation.get("aligned_entities", [])[:10]
        entity_summaries = [
            {
                "name": e.get("name"),
                "role": e.get("role"),
                "heat": e.get("heat"),
                "sentiment": e.get("sentiment"),
                "top_issues": [
                    f.get("text") for f in (e.get("top_issues") or [])[:3]
                    if isinstance(f, dict) and f.get("text")
                ],
            }
            for e in entities
        ]

        # 话题 top 15（精简字段）
        topics = foundation.get("aligned_topics", [])[:15]
        topic_summaries = [
            {
                "name": t.get("name"),
                "category": t.get("category"),
                "heat": t.get("heat"),
                "sentiment": t.get("sentiment"),
            }
            for t in topics
        ]

        # Landscape 层 — SOV top 10（仅 name+share）
        landscape = layers.get("landscape") or {}
        sov_ranking = landscape.get("sov_ranking", [])[:10]
        sov_brief = [
            {"name": r.get("name"), "share": r.get("share")}
            for r in sov_ranking
        ]

        # Intent 层 — topic_radar (pains/gains/controversies) + unmet_needs
        intent = layers.get("intent") or {}
        unmet_needs = intent.get("unmet_needs")

        # topic_radar：按情感分桶的话题（Tension 的核心数据源）
        topic_radar = intent.get("topic_radar") or {}
        pains_brief = [
            {"name": p.get("name"), "heat": p.get("heat"), "sentiment": p.get("sentiment")}
            for p in (topic_radar.get("pains") or [])[:10]
            if isinstance(p, dict)
        ]
        controversies_brief = [
            {"name": c.get("name"), "heat": c.get("heat"),
             "positive_mentions": c.get("positive_mentions"),
             "negative_mentions": c.get("negative_mentions")}
            for c in (topic_radar.get("controversies") or [])[:5]
            if isinstance(c, dict)
        ]
        gains_brief = [
            {"name": g.get("name"), "heat": g.get("heat"), "sentiment": g.get("sentiment")}
            for g in (topic_radar.get("gains") or [])[:5]
            if isinstance(g, dict)
        ]

        # Focus 层 — SWOT 维度摘要（含 delta 表示优劣势程度）+ Gap 盲区
        focus = layers.get("focus") or {}
        swot = focus.get("swot") or {}
        swot_brief = None
        if swot:
            swot_brief = {
                k: [
                    {"dimension": d.get("dimension"), "delta": d.get("delta")}
                    for d in dims[:5]
                    if isinstance(d, dict)
                ]
                for k, dims in swot.items()
                if isinstance(dims, list) and dims
            }

        # Gap：竞品强项但目标品牌盲区的维度（Brand Opportunity 的核心数据源）
        gap_dims = (focus.get("gap") or {}).get("dimensions") or []
        gap_brief = [
            {
                "dimension": g.get("dimension"),
                "competitor_sentiment": g.get("competitor_sentiment"),
                "competitor_mentions": g.get("competitor_mentions"),
                "target_mentions": g.get("target_mentions"),
            }
            for g in gap_dims[:5]
            if isinstance(g, dict)
        ]

        part: dict[str, Any] = {
            "slice_index": i,
            "meta": {
                "subject": meta.get("subject"),
                "competitors": meta.get("competitors"),
            },
            "entities": entity_summaries,
            "topics": topic_summaries,
            "sov_ranking": sov_brief,
            "unmet_needs": unmet_needs,
        }
        # 条件添加非空字段（控制 token 量）
        if pains_brief:
            part["pains"] = pains_brief
        if controversies_brief:
            part["controversies"] = controversies_brief
        if gains_brief:
            part["gains"] = gains_brief
        if swot_brief:
            part["swot_dimensions"] = swot_brief
        if gap_brief:
            part["competitive_gaps"] = gap_brief
        slice_parts.append(part)

    return {
        "brief_section": brief_section,
        "consult_summary": consult_summary,
        "evaluation_summary": evaluation_summary,
        "slice_data": json.dumps(slice_parts, ensure_ascii=False, indent=2),
    }


def parse_phase1_response(response_text: str) -> dict[str, Any]:
    """解析 Phase 1 LLM 输出"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Phase 1 JSON 解析失败: %s...", text[:200])
        return {"social_tensions": [], "brand_opportunities": []}

    # 确保字段存在
    if "social_tensions" not in result:
        result["social_tensions"] = []
    if "brand_opportunities" not in result:
        result["brand_opportunities"] = []

    return result
