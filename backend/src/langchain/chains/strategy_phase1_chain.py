"""Strategy Phase 1 Chain — 洞察层: Social Tension + Brand Opportunity

从切片数据中提取社会矛盾/未满足需求，及品牌可切入的机会。

## 输入上下文（USER_TEMPLATE 的四个占位符）

- brief_section     : 品牌 Brief（目标/竞品/关注维度），来自 strategy.brand_brief
- research_context_section: 研究问题 + 需求理解摘要，来自 strategy.research_design
- slice_data        : 所有关联切片的聚合分析数据，由 format_slice_data_for_phase1() 构建

## 关键设计决策

1. **跨切片异常预计算在 Python 层完成（_compute_cross_slice_anomalies）**
   - 检测同一实体跨切片情感落差（|delta| >= 0.5）
   - 原因：字符串精确匹配比 LLM 推断更精准，且节省 token；话题名称跨切片不一致，
     改由 LLM 凭完整数据自行判断话题交叉，避免误报
   - 预计算结果以自然语言 hint 注入 slice_data，不依赖 LLM 重新发现

2. **Prompt 强制要求"反直觉"洞察，而非通用观察**
   - 每条 Tension 必须说明 conventional_wisdom（行业常识）与 data_reality（数据反驳）
   - 至少 1 条 Tension 须跨 ≥2 个切片，防止单切片视角的幸存者偏差
   - "用户关注健康"类宽泛结论被明确禁止，倒逼 LLM 寻找真正的数据异常

3. **采样偏置提示注入 SYSTEM_TEMPLATE**
   - 品牌聚焦切片（有 subject）关键词含品牌名，该品牌实体热度必然虚高
   - 竞品 SOV 判断须以大盘切片（无 subject）为准
   - 这条规则防止 LLM 误用偏置切片数据得出错误的竞争格局结论

4. **模型选用 chat（非 reasoner）**
   - DeepSeek R1（reasoner）的思考 token 与输出 token 共享 max_tokens=65536
   - 多切片数据导致输入大，R1 思考过多后输出截断，JSON 解析失败
   - chat 模型输出质量在该任务上等同或更优（洞察质量由 prompt 约束而非 CoT 保证）
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

## 洞察质量标准（重要）

**核心要求：输出不能是"认真浏览一遍内容就能得出"的结论。**

优先挖掘以下类型的洞察：
1. **反常信号**：热度高但情感负向（争议核心）、热度低但情感极正向（潜在机会）、跨切片同一实体情感截然相反（场景依赖）
2. **跨切片交叉洞察**：只有对比 ≥2 个切片才能发现的模式，至少 1 条 Tension 必须满足此要求，并在 evidence 中说明单看任一切片无法得出该结论
3. **常识颠覆**：每条结论须明确说明它如何修正行业通常认知，不接受"用户关注健康"此类任何人都能猜到的结论

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "social_tensions": [
    {{
      "statement": "一句话描述该矛盾",
      "conventional_wisdom": "行业从业者通常会认为什么（一句话）",
      "data_reality": "但数据揭示了什么不同的事实，以及为何反直觉（一句话）",
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
      "why_non_obvious": "为什么这个机会不是显而易见的，以及竞品为何尚未占据此位置",
      "evidence": [
        {{"type": "sov_gap", "description": "具体数据发现", "source": "slice数据"}}
      ],
      "related_tensions": [0]
    }}
  ]
}}

## 要求
- social_tensions: 1-3 条，按重要性排序；至少 1 条须引用 ≥2 个切片的交叉数据
- brand_opportunities: 1-2 条，每条引用相关 tension 的索引
- evidence 至少 2 条，类型可选: topic_sentiment, opinion_cluster, sov_gap, quadrant_position, kol_voice, unmet_need, audience_insight, organic_vs_mixed_sentiment, topic_category_pattern
- confidence: high(数据充分)/medium(有支撑但需验证)/low(推测性)
- 如切片数据中包含 audiences（受众画像），需标注哪类人群最受此 Tension 影响，以及哪类人群是品牌机会的主要触达对象

## 字段解读

- **original_terms**（top 5 实体）：用户提及该实体时的原始表述（最多 3 条），保留真实语言模式，evidence 可直接引用原话以增强说服力。
- **organic_sentiment**（实体/话题/pains/gains）：剔除推广内容后的真实用户情感。若与 sentiment 差距 >= 0.2，说明推广内容正在掩盖真实口碑，优先以 organic_sentiment 为准。
- **sov_ranking[].sentiment**：各品牌声量份额（share）配合情感，可定位四象限：高声量低情感是竞品弱点，低声量高情感是品牌机会入口。
- **controversies[].controversy_depth**：两极均衡度（0~0.5，越接近 0.5 说明正负意见越均衡、越撕裂）。真正的核心矛盾往往 depth 高但 heat 未必高。**仅当 `polar_total >= 10` 时样本可信**，polar_total 过低时应降低置信度。
- **pains[].organic_sentiment**：关注 `organic_sentiment` 明显低于 `sentiment` 的痛点话题（差值 >= 0.2），说明该话题被推广内容稀释，真实用户体验比数字所呈现的更差，是高价值的隐性痛点信号。
- **topic_aspects**：按主题类别聚合的宏观分布，用于发现「某一整类话题情感集体偏负」等品类级模式，是单话题视图看不到的。

## 切片采样偏置（重要）

每个切片的数据范围由其采集关键词决定，分析时须考虑采样偏置：

- **品牌聚焦切片**（有 subject）：关键词通常含品牌名，该品牌的实体热度必然偏高，**不能直接用于判断市场竞争格局或品牌真实声量占比**
- **大盘分析切片**（无 subject）：关键词为品类词/场景词，SOV 排名更接近真实市场声量分布，**竞品格局分析以大盘切片的 SOV 为准**
- 同一品牌在品牌聚焦切片里热度高，在大盘切片里 SOV 不高，属正常现象，不构成矛盾
- Brand Opportunity 中的竞品空白区判断，优先引用大盘切片的 sov_gap 或 quadrant_position，而非品牌聚焦切片的实体热度排名
"""

USER_TEMPLATE = """{brief_section}

{research_context_section}


## 切片数据

{slice_data}"""


def create_strategy_phase1_chain() -> Runnable:
    """创建 Phase 1 (洞察层) LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def _compute_cross_slice_anomalies(slice_parts: list[dict]) -> list[dict]:
    """跨切片异常信号预计算（纯代码，无 LLM 成本）

    检测实体情感落差：同一实体在不同切片中情感差异显著（|delta| >= 0.5），
    说明该实体的口碑具有场景/人群依赖性，是值得深挖的交叉洞察线索。

    注：话题覆盖空白不在此处计算——话题名称跨切片不保证一致，
    精确字符串匹配会产生大量误报，由 LLM 凭完整数据自行判断更准确。
    """
    if len(slice_parts) < 2:
        return []

    entity_sentiment_map: dict[str, list[dict]] = {}
    for s in slice_parts:
        for e in s.get("entities") or []:
            name = e.get("name")
            sentiment = e.get("sentiment")
            if name and sentiment is not None:
                entity_sentiment_map.setdefault(name, []).append({
                    "slice_index": s["slice_index"],
                    "mode": s["mode"],
                    "sentiment": sentiment,
                })

    anomalies: list[dict] = []
    for name, records in entity_sentiment_map.items():
        if len(records) < 2:
            continue
        sentiments = [r["sentiment"] for r in records]
        delta = max(sentiments) - min(sentiments)
        if delta >= 0.5:
            anomalies.append({
                "type": "entity_sentiment_divergence",
                "entity": name,
                "delta": round(delta, 2),
                "detail": records,
                "insight_hint": (
                    f"「{name}」跨切片情感落差 {delta:.2f}，"
                    "可能反映场景/人群差异，值得交叉分析"
                ),
            })

    # 按落差降序，最多返回 5 条
    anomalies.sort(key=lambda x: x["delta"], reverse=True)
    return anomalies[:5]


def _build_research_context_section(
    research_design: dict | None = None,
) -> str:
    """构建研究上下文摘要（研究问题 + 需求理解）"""
    if not research_design:
        return ""

    lines = ["## 研究问题（本次分析要回答的核心问题）"]
    for rq in research_design.get("research_questions", []):
        lines.append(
            f"- [{rq.get('id')}] {rq.get('question')} "
            f"(维度: {rq.get('dimension')}, 优先级: {rq.get('priority', 'medium')})"
        )
    summary = research_design.get("understanding_summary", "")
    if summary:
        lines.append(f"\n## 需求理解摘要\n{summary}")
    return "\n".join(lines)


def format_slice_data_for_phase1(
    slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
) -> dict[str, Any]:
    """将切片 result_data 格式化为 Phase 1 输入

    从每个切片提取关键维度，严格控制总输入 ~30K tokens。
    结构化数据优先，按 Tension/Opportunity 两个产出目标精选字段。
    """
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    research_context_section = _build_research_context_section(research_design)

    def _controversy_depth(c: dict) -> float:
        """两极均衡度：0~0.5，越接近 0.5 说明正负意见越均衡（越撕裂）。"""
        pos = int(c.get("positive_mentions") or 0)
        neg = int(c.get("negative_mentions") or 0)
        total = pos + neg
        return min(pos, neg) / total if total > 0 else 0.0

    slice_parts = []
    for i, s in enumerate(slices):
        meta = s.get("meta") or {}
        foundation = s.get("foundation") or {}
        layers = s.get("layers") or {}

        # 实体 top 10（精简字段 + issues 用于 Opportunity 推导竞品弱点）
        # organic_sentiment：剔除推广内容后的真实用户情感，与 sentiment 差距大时说明推广掩盖了真实口碑
        # original_terms（top 5 实体）：用户原始表述，保留真实语言模式，供 evidence 引用原话
        entities = foundation.get("aligned_entities", [])[:10]
        entity_summaries = []
        for idx_e, e in enumerate(entities):
            entry: dict[str, Any] = {
                "name": e.get("name"),
                "role": e.get("role"),
                "heat": e.get("heat"),
                "sentiment": e.get("sentiment"),
                "organic_sentiment": e.get("organic_sentiment"),
                "top_issues": [
                    f.get("text") for f in (e.get("top_issues") or [])[:3]
                    if isinstance(f, dict) and f.get("text")
                ],
            }
            # 仅为 top 5 实体附加原始用语，避免 token 过载
            if idx_e < 5:
                raw_terms = e.get("original_terms") or []
                terms = [
                    (t if isinstance(t, str) else t.get("text", ""))
                    for t in raw_terms[:3]
                    if t
                ]
                if terms:
                    entry["original_terms"] = terms
            entity_summaries.append(entry)

        # 话题 top 15（精简字段）
        # organic_sentiment：有机内容下的话题情感，比混合均值更反映真实用户态度
        topics = foundation.get("aligned_topics", [])[:15]
        topic_summaries = [
            {
                "name": t.get("name"),
                "category": t.get("category"),
                "heat": t.get("heat"),
                "sentiment": t.get("sentiment"),
                "organic_sentiment": t.get("organic_sentiment"),
            }
            for t in topics
        ]

        # Landscape 层 — SOV top 10（name + share + sentiment，可推导四象限位置）
        landscape = layers.get("landscape") or {}
        sov_ranking = landscape.get("sov_ranking", [])[:10]
        sov_brief = [
            {
                "name": r.get("name"),
                "share": r.get("share"),
                "sentiment": r.get("sentiment"),
                "role": r.get("role"),
            }
            for r in sov_ranking
        ]

        # Intent 层 — topic_radar (pains/gains/controversies) + unmet_needs + audiences
        intent = layers.get("intent") or {}
        unmet_needs = intent.get("unmet_needs")

        # 受众画像（Social Tension 的人群锚点 + Brand Opportunity 的目标受众）
        context_analysis = intent.get("context_analysis") or {}
        audiences_raw = context_analysis.get("audiences") or []
        audiences_brief = [
            {
                "label": a.get("label"),
                "heat": a.get("heat"),
                "mentions": a.get("mentions"),
                "preferences": (a.get("preferences") or [])[:3],
            }
            for a in audiences_raw[:8]
            if isinstance(a, dict) and a.get("label")
        ]

        # topic_radar：按情感分桶的话题（Tension 的核心数据源）
        # pains/gains 加入 organic_sentiment，区分真实痛点与被推广放大的声音
        topic_radar = intent.get("topic_radar") or {}
        pains_brief = [
            {
                "name": p.get("name"),
                "heat": p.get("heat"),
                "sentiment": p.get("sentiment"),
                "organic_sentiment": p.get("organic_sentiment"),
            }
            for p in (topic_radar.get("pains") or [])[:10]
            if isinstance(p, dict)
        ]

        # controversies 按两极均衡度降序排列（min/total 越接近 0.5 越撕裂），而非热度
        # 这样能找到真正意见分裂的话题，而非仅仅讨论量大的话题
        controversies_sorted = sorted(
            [c for c in (topic_radar.get("controversies") or []) if isinstance(c, dict)],
            key=_controversy_depth,
            reverse=True,
        )
        controversies_brief = [
            {
                "name": c.get("name"),
                "heat": c.get("heat"),
                "polar_total": int(c.get("polar_total") or 0),
                "positive_mentions": c.get("positive_mentions"),
                "negative_mentions": c.get("negative_mentions"),
                "controversy_depth": round(_controversy_depth(c), 2),
            }
            for c in controversies_sorted[:8]
        ]

        gains_brief = [
            {
                "name": g.get("name"),
                "heat": g.get("heat"),
                "sentiment": g.get("sentiment"),
                "organic_sentiment": g.get("organic_sentiment"),
            }
            for g in (topic_radar.get("gains") or [])[:5]
            if isinstance(g, dict)
        ]

        # 主题类别概览：按 category 聚合的宏观分布（热度+情感），补充单话题视图的盲区
        topic_aspects_brief = [
            {
                "category": a.get("category"),
                "heat": a.get("heat"),
                "sentiment": a.get("sentiment"),
                "mention_count": a.get("mention_count"),
                "representative_topics": (a.get("representative_topics") or [])[:4],
            }
            for a in (intent.get("topic_aspects") or [])[:5]
            if isinstance(a, dict) and a.get("category")
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

        subject = meta.get("subject") or None
        part: dict[str, Any] = {
            "slice_index": i,
            "mode": "品牌聚焦" if subject else "大盘分析",
            "subject": subject,
            "competitors": meta.get("competitors"),
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
        if topic_aspects_brief:
            part["topic_aspects"] = topic_aspects_brief
        if swot_brief:
            part["swot_dimensions"] = swot_brief
        if gap_brief:
            part["competitive_gaps"] = gap_brief
        if audiences_brief:
            part["audiences"] = audiences_brief
        slice_parts.append(part)

    cross_slice_anomalies = _compute_cross_slice_anomalies(slice_parts)

    slice_data = json.dumps(slice_parts, ensure_ascii=False, indent=2)
    if cross_slice_anomalies:
        slice_data += (
            "\n\n## 跨切片异常信号（代码预计算，供交叉洞察参考）\n"
            + json.dumps(cross_slice_anomalies, ensure_ascii=False, indent=2)
        )

    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "slice_data": slice_data,
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
