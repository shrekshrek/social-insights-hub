"""Strategy Insight Chain — 洞察层: Social Tension + Brand Opportunity

brand_strategy 三阶段递进分析的**第 1 层**：insight → brand_role → big_idea。
本层消费切片原始数据，产出 tensions / opportunities 供下游 brand_role 层使用。

从切片数据中提取社会矛盾/未满足需求，及品牌可切入的机会。

## 两种运行模式

- **campaign_strategy 模式**：社媒切片为主源，新闻数据作为补充证据
- **full_strategy 模式**：在 campaign_strategy 基础上，**额外**注入
  Landscape 竞争格局分析作为对标参考。原始新闻切片仍然完整保留——
  Landscape 是**已结构化的二阶解读**（players / positioning_map / battles），
  原始新闻是**一阶事实信号**（entities / quotes / event_clusters 时序），
  两者地位不同，互为补充而非替代。消费者-媒体分歧仍是 full_strategy
  模式下最高价值的 Tension 来源，但应基于原始新闻信号识别，Landscape
  仅作为"竞品已占据/未占据的位置"对标参考。

## 输入上下文（USER_TEMPLATE 的占位符）

- brief_section     : 品牌 Brief（目标/竞品/关注维度），来自 strategy.brand_brief
- research_context_section: 研究问题 + 需求理解摘要，来自 strategy.research_design
- coverage_signals  : 跨切片数据质量诊断（warnings + data_highlights），来自
                      strategy.coverage_check_result，用于校准结论置信度
- slice_data        : 所有关联切片的聚合分析数据，由 format_slice_data_for_insight() 构建
- news_media_section: 新闻切片补充段落（campaign / full_strategy 都注入原始数据）
- landscape_context_section: 仅 full_strategy 注入 Landscape 已结构化的
                      竞争格局对标参考，campaign_strategy 下为空字符串

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

from src.llm.chains.strategy.research_findings import format_coverage_signals
from src.llm.llm import get_llm

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

## 实体级关键字段（用于多层 tension 识别）

数据中实体含以下扩展字段，每个字段明确指向**特定层面的 tension**：

- **`top_issues`**（top 10 实体均有）：用户对该实体的痛点/不满 → **产品层 tension**（功能缺陷、体验落差）
- **`top_scenarios`**（top 10 实体均有）：该实体被讨论的常见使用场景 → **场景层 tension**（特定场景下的痛点、场景缺失、场景不便）
- **`top_market_factors`**（top 10 实体均有）：消费者讨论时的宏观背景（价格/政策/经济环境/促销/渠道） → **宏观层 tension**（消费降级、价格敏感、政策影响等大背景下的需求转变）

不同层面的 tension 价值不同：
- 产品层 tension 易被竞品复制（短期机会）
- 场景层 tension 更具差异化（中期占位）
- 宏观层 tension 与品牌大方向绑定（长期定位价值）

**关键识别方法**：
- **跨实体场景重叠** = 高价值场景层 tension（多个品牌都在同一场景被讨论且都有问题，说明是行业级场景痛点而非单品牌问题）
- **跨实体宏观重叠** = 高价值宏观层 tension（多个品牌讨论中共同出现某宏观因素，说明是行业级背景驱动的需求转变）

**优先挖掘场景层和宏观层 tension** —— 仅基于 issues 的产品层 tension 容易停留在表层。

## 洞察质量标准（重要）

**核心要求：输出不能是"认真浏览一遍内容就能得出"的结论。**

优先挖掘以下类型的洞察：
1. **反常信号**：热度高但情感负向（争议核心）、热度低但情感极正向（潜在机会）、跨切片同一实体情感截然相反（场景依赖）
2. **跨切片交叉洞察**：只有对比 ≥2 个切片才能发现的模式，至少 1 条 Tension 必须满足此要求，并在 evidence 中说明单看任一切片无法得出该结论
3. **常识颠覆**：每条结论须明确说明它如何修正行业通常认知，不接受"用户关注健康"此类任何人都能猜到的结论
4. **多层 tension 覆盖**：1-3 条 tension 中应该至少有 1 条属于"场景层"或"宏观层"，不要全部停留在"产品层"

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "social_tensions": [
    {{
      "statement": "一句话描述该矛盾",
      "conventional_wisdom": "行业从业者通常会认为什么（一句话）",
      "data_reality": "但数据揭示了什么不同的事实，以及为何反直觉（一句话）",
      "evidence": [
        {{"type": "topic_sentiment", "description": "具体数据发现", "source": "<取自切片 _source_label>"}},
        {{"type": "opinion_cluster", "description": "具体数据发现", "source": "<取自切片 _source_label>"}}
      ],
      "confidence": "high/medium/low",
      "research_questions_addressed": ["rq1", "rq3"]
    }}
  ],
  "brand_opportunities": [
    {{
      "statement": "一句话描述品牌机会",
      "why_non_obvious": "为什么这个机会不是显而易见的，以及竞品为何尚未占据此位置",
      "evidence": [
        {{"type": "sov_gap", "description": "具体数据发现", "source": "<取自切片 _source_label>"}}
      ],
      "related_tensions": [0],
      "research_questions_addressed": ["rq2"]
    }}
  ]
}}

## evidence.source 来源约束

每条 evidence.source 必须填具体可追溯标签：
- 切片：取切片对象 `_source_label` 字段值（如 `Social Slice #0: ...` / `News Slice #0: ...`）
- 行业研究：`Research: <主题>`
- Landscape 二阶解读（仅 full_strategy 路径）：`Landscape: players[<i>]` / `Landscape: positioning_map`

## 要求
- social_tensions: 1-3 条，按重要性排序；至少 1 条须引用 ≥2 个切片的交叉数据
- brand_opportunities: 1-2 条，每条引用相关 tension 的索引
- evidence 至少 2 条，类型可选: topic_sentiment, opinion_cluster, sov_gap, quadrant_position, kol_voice, unmet_need, audience_insight, organic_vs_mixed_sentiment, topic_category_pattern
- confidence: high(数据充分)/medium(有支撑但需验证)/low(推测性)
- **research_questions_addressed（必填）**：每条 tension / opportunity 必须用 RQ id 列表标明它回应了 research_context_section 中的哪些 RQ；若结论是数据中浮现的额外洞察、不直接对应任何 RQ，填空数组 `[]`，但**不要漏写字段**
- 若 `coverage_signals` 段落对某 RQ 标注了「数据稀疏/警告」，回应该 RQ 的 tension/opportunity 必须使用 hedging 措辞（如"初步迹象"、"有限数据显示"），不得做强断言
- 如切片数据中包含 audiences（受众画像），需标注哪类人群最受此 Tension 影响，以及哪类人群是品牌机会的主要触达对象

## 字段解读

- **original_terms**（top 5 实体）：用户提及该实体时的原始表述（最多 3 条），保留真实语言模式，evidence 可直接引用原话以增强说服力。
- **organic_sentiment**（实体/话题/pains/gains）：剔除推广内容后的真实用户情感。若与 sentiment 差距 >= 0.2，说明推广内容正在掩盖真实口碑，优先以 organic_sentiment 为准。
- **sov_ranking[].sentiment**：各品牌声量份额（share）配合情感，可定位四象限：高声量低情感是竞品弱点，低声量高情感是品牌机会入口。
- **sov_ranking[].organic_heat / promo_heat**：自然声量 vs 推广声量。**判断品牌真实竞争声量优先看 organic_heat**（share 是 organic+promo 合计，会被推广拉高）。多数品牌 organic 主导、属正常；仅当某品牌 promo_heat 显著高于 organic_heat 时，说明其 share 主要由推广（软广/种草）堆出，需相应下调对其声量的采信——**不预设、不臆造**。（与 organic_sentiment 同理：声量看 organic_heat、情感看 organic_sentiment。）
- **controversies[].controversy_depth**：两极均衡度（0~0.5，越接近 0.5 说明正负意见越均衡、越撕裂）。真正的核心矛盾往往 depth 高但 heat 未必高。**仅当 `polar_total >= 10` 时样本可信**，polar_total 过低时应降低置信度。
- **pains[].organic_sentiment**：关注 `organic_sentiment` 明显低于 `sentiment` 的痛点话题（差值 >= 0.2），说明该话题被推广内容稀释，真实用户体验比数字所呈现的更差，是高价值的隐性痛点信号。
- **topic_aspects**：按主题类别聚合的宏观分布，用于发现「某一整类话题情感集体偏负」等品类级模式，是单话题视图看不到的。
- **group_share**：按母品牌族聚合的声量份额（个体 sov 之上的组级视图）。当多个子品牌同属一个集团时，组级份额比单品牌 sov 更能反映真实竞争格局——判断"谁主导品类"应参考 group_share 而非仅看单实体。
- **entity_dimension_matrix**：主体与竞品在各产品维度上的逐项情感（含提及量），用于细粒度逐属性竞争定位——可锁定「竞品某维度口碑强而主体弱」的具体攻防点，比 competitive_gaps 的降维投影更细，适合支撑 brand_opportunity。

## 切片采样偏置（重要）

每个切片的数据范围由其采集关键词决定，分析时须考虑采样偏置：

- **品牌聚焦切片**（有 subject）：关键词通常含品牌名，该品牌的实体热度必然偏高，**不能直接用于判断市场竞争格局或品牌真实声量占比**
- **大盘分析切片**（无 subject）：关键词为品类词/场景词，SOV 排名更接近真实市场声量分布，**竞品格局分析以大盘切片的 SOV 为准**
- 同一品牌在品牌聚焦切片里热度高，在大盘切片里 SOV 不高，属正常现象，不构成矛盾
- Brand Opportunity 中的竞品空白区判断，优先引用大盘切片的 sov_gap 或 quadrant_position，而非品牌聚焦切片的实体热度排名

## 新闻媒体数据使用指南

如果输入包含"新闻媒体视角"数据，请注意：
- 新闻数据来自搜索引擎聚合（百度/搜狗）和微信公众号，反映**媒体/行业视角**，与社媒切片中的**消费者视角**互为补充
- **交叉验证**：当社媒消费者声音与新闻媒体报道出现矛盾时（如消费者负面但媒体正面），这本身就是高价值的 Tension 线索
- **叙事聚类**（narratives）反映媒体如何定义和包装品类议题，可能与消费者实际关注点存在偏差
- **实体角色**：新闻中的实体角色（target/competitor/context）代表媒体视角的竞争定位，与社媒 SOV 排名可能不同
- 新闻数据作为**补充证据**使用，不要仅凭新闻数据得出 Tension 结论——Tension 的核心依据应来自消费者真实声音（社媒切片），新闻数据用于验证或补充

## 行业研究数据（research_findings）使用指南

- 行业研究数据来自自动化搜索引擎 + 行业报告 + 公开数据的综合分析，代表**专家/行业视角**
- 与社媒消费者声音、新闻媒体报道构成**三位一体**的分析视角：消费者声音（社媒）→ 媒体叙事（新闻）→ 行业事实（研究）
- **交叉验证优先**：当研究数据与社媒/新闻数据出现矛盾时（如行业增长但消费者不满），这本身就是高价值的 Tension 线索
- 研究数据中的**置信度**标记（high/medium/low）反映证据充分程度，high 数据可直接引用，low 数据需其他来源佐证
- 如 `{{research_findings}}` 段落为空，**正常忽略**该部分，仅基于切片和新闻数据进行分析
"""

USER_TEMPLATE = """{brief_section}

{research_context_section}

{coverage_signals}

{research_findings}

## 切片数据

{slice_data}

{news_media_section}

{landscape_context_section}"""


def create_insight_chain() -> Runnable:
    """创建 Insight (洞察层) LLM 链 — brand_strategy 三阶段第 1 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            ("user", USER_TEMPLATE),
        ]
    )
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
                entity_sentiment_map.setdefault(name, []).append(
                    {
                        "slice_index": s["slice_index"],
                        "mode": s["mode"],
                        "sentiment": sentiment,
                    }
                )

    anomalies: list[dict] = []
    for name, records in entity_sentiment_map.items():
        if len(records) < 2:
            continue
        sentiments = [r["sentiment"] for r in records]
        delta = max(sentiments) - min(sentiments)
        if delta >= 0.5:
            anomalies.append(
                {
                    "type": "entity_sentiment_divergence",
                    "entity": name,
                    "delta": round(delta, 2),
                    "detail": records,
                    "insight_hint": (
                        f"「{name}」跨切片情感落差 {delta:.2f}，"
                        "可能反映场景/人群差异，值得交叉分析"
                    ),
                }
            )

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


def _format_news_media_section(
    news_slices: list[dict],
    news_slice_refs: list[dict] | None = None,
) -> str:
    """从 NewsSlice 数据格式化新闻媒体视角补充段落（ADR-003 新 schema）。

    只消费**结构化数据**（descriptive / entities / quotes / media_landscape /
    competitive / event_clusters），不消费 page_synthesis（LLM 散文）。

    `news_slice_refs` 与 news_slices 一一对应，提供 slice 显示标签 `News Slice #i: <name>`
    供 LLM 在 evidence.source 中精准引用，便于前端反查上游数据。
    """
    all_insights: list[dict] = []
    for idx, ns in enumerate(news_slices):
        rd = ns.get("result_data")
        if not rd or isinstance(rd, str):
            continue
        descriptive = rd.get("descriptive") or {}
        media_landscape = rd.get("media_landscape") or {}
        competitive = rd.get("competitive") or {}

        # 优先用 refs 中的 name（与 service 层加载顺序对齐）兜底回 ns.name
        ref_name = (
            news_slice_refs[idx].get("name")
            if news_slice_refs and idx < len(news_slice_refs)
            else None
        )
        slice_label = ref_name or ns.get("name") or ""
        all_insights.append(
            {
                "_source_label": f"News Slice #{idx}: {slice_label}".strip(": "),
                "slice_name": slice_label,
                "article_count": descriptive.get("articles_filtered", 0),
                "source_tier_distribution": descriptive.get("source_tier_distribution"),
                "sentiment_overall": descriptive.get("sentiment_overall"),
                "sentiment_by_tier": descriptive.get("sentiment_by_tier"),
                "source_pyramid": media_landscape.get("source_pyramid"),
                # 实体清单（已归一 + role 标注）
                "entities": [
                    {
                        "name": e.get("name"),
                        "role": e.get("role"),
                        "mention_count": e.get("mention_count"),
                        "source_count": e.get("source_count"),
                        "cross_task_count": e.get("cross_task_count"),
                        "sentiment_avg": e.get("sentiment_avg"),
                        "sentiment_by_tier": e.get("sentiment_by_tier"),
                    }
                    # 新闻切片 entities 上限 30（pass1_chain），取 [:15] 覆盖 target+competitor+
                    # 高 mention context；规模上限 30 时 [:15] 已含全部 source>=2 实体
                    for e in (rd.get("entities") or [])[:15]
                ],
                # 引述（已 speaker 分级，原文 + 来源 + 文章 ID 锚点）
                "key_quotes": [
                    {
                        "speaker": q.get("speaker"),
                        "speaker_role": q.get("speaker_role"),
                        "quote": q.get("quote"),
                        "source_name": q.get("source_name"),
                        "source_tier": q.get("source_tier"),
                    }
                    # Pass 1 quotes 上限 12，取 [:12] = 全部高分级 quote
                    for q in (rd.get("quotes") or [])[:12]
                    if q.get("speaker_role") in ("official", "executive", "analyst")
                ],
                # 议题层（媒体反复讨论的抽象维度 + 态度）——与社媒 aligned_topics 同构，
                # 是消费者-媒体分歧识别的直接对照面；字段口径与 agenda_map/landscape 一致
                "themes": [
                    {
                        "name": t.get("name"),
                        "article_count": t.get("article_count"),
                        "source_count": t.get("source_count"),
                        "sentiment_avg": t.get("sentiment_avg"),
                        "tier_weighted_score": t.get("tier_weighted_score"),
                    }
                    # pass1 上限 8，取 [:8] = 全部议题
                    for t in (rd.get("themes") or [])[:8]
                    if isinstance(t, dict) and t.get("name")
                ],
                # 竞争投影（target / competitor 子集）
                "competitive": {
                    "players": competitive.get("players"),
                    "quote_share": competitive.get("quote_share"),
                },
            }
        )

    if not all_insights:
        return ""

    return (
        "## 新闻媒体视角（补充数据）\n\n"
        "以下数据来自新闻媒体渠道（搜索引擎聚合 + 微信公众号），反映媒体/行业对相关话题的报道视角，"
        "与社媒切片中的消费者声音互为补充。**结构化数据**：含归一后实体（带 role / "
        "by_tier sentiment）+ 分级引述（official/executive/analyst）+ 议题（themes，媒体反复"
        "讨论的抽象维度 + 态度，可与社媒话题直接对照识别消费者-媒体分歧；注意其 sentiment 量纲"
        "为 [-2,2]，与社媒话题不同）+ 媒介金字塔 + 竞争投影。\n\n"
        + json.dumps(all_insights, ensure_ascii=False, indent=2)
    )


def format_slice_data_for_insight(
    slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slices: list[dict] | None = None,
    slice_refs: list[dict] | None = None,
    news_slice_refs: list[dict] | None = None,
    research_findings: str = "",
    coverage_check_result: dict | None = None,
) -> dict[str, Any]:
    """将切片 result_data 格式化为 Insight (洞察层) 输入

    从每个切片提取关键维度，严格控制总输入 ~30K tokens。
    结构化数据优先，按 Tension/Opportunity 两个产出目标精选字段。

    `slice_refs` / `news_slice_refs` 与 slices / news_slices 一一对应（同序），
    提供 slice 显示标签 `Social Slice #i: <name>` / `News Slice #i: <name>`
    供 LLM 在 evidence.source 中精准引用。缺省时退化为 "Slice #i" 不带名称。
    """
    brief_section = ""
    if brief:
        brief_section = (
            f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        )

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

        # 实体 top 50（精简字段 + issues 用于 Opportunity 推导竞品弱点）
        # organic_sentiment：剔除推广内容后的真实用户情感，与 sentiment 差距大时说明推广掩盖了真实口碑
        # 字段附加范围分级（基于"信号广度 vs 数据稀疏度"权衡）：
        #   - original_terms（top 5）：用户原话，长尾实体原话稀疏不具代表性，仅 top 5 有意义
        #   - top_scenarios（top 10）：场景层 tension 需"跨实体场景重叠"识别，需广覆盖
        #   - top_market_factors（top 10）：宏观层 tension 需"跨实体宏观重叠"识别，需广覆盖
        # 窗口 50 依据：aligned_entities 按 score 降序，top 10 几乎全是品牌实体（Target/Competitor），
        # Context 角色（成分/技术/概念实体）从 top 11 起，扩到 50 覆盖 source>=3 的全部 Context
        entities = foundation.get("aligned_entities", [])[:50]
        entity_summaries = []
        for idx_e, e in enumerate(entities):
            entry: dict[str, Any] = {
                "name": e.get("name"),
                "role": e.get("role"),
                "heat": e.get("heat"),
                "sentiment": e.get("sentiment"),
                "organic_sentiment": e.get("organic_sentiment"),
                "top_issues": [
                    f.get("text")
                    for f in (e.get("top_issues") or [])[:3]
                    if isinstance(f, dict) and f.get("text")
                ],
            }

            # 场景层 + 宏观层 tension 字段（top 10 全覆盖）
            scenarios = [
                s.get("text")
                for s in (e.get("top_scenarios") or [])[:3]
                if isinstance(s, dict) and s.get("text")
            ]
            if scenarios:
                entry["top_scenarios"] = scenarios

            market_factors = [
                m.get("text")
                for m in (e.get("top_market_factors") or [])[:3]
                if isinstance(m, dict) and m.get("text")
            ]
            if market_factors:
                entry["top_market_factors"] = market_factors

            # 用户原话仅 top 5（长尾稀疏不具代表性）
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

        # 话题 top 30（精简字段）
        # organic_sentiment：有机内容下的话题情感，比混合均值更反映真实用户态度
        # 窗口 30 依据：aligned_topics 按 score 降序，top 30 仍 100% source>=3，
        # 且能纳入成分/技术等概念话题；top 50 后 source>=3 占比断崖（1/50 噪声混入）
        topics = foundation.get("aligned_topics", [])[:30]
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

        # Landscape 层 — SOV top 10（按 share 降序截取；名次物化为字段，LLM 直读不重排。
        # sov_ranking 的存储序并非严格按 share 单调，不能按列表位置读名次）
        landscape = layers.get("landscape") or {}
        sov_all = [
            r for r in (landscape.get("sov_ranking") or []) if isinstance(r, dict)
        ]
        sov_sorted = sorted(sov_all, key=lambda r: r.get("share") or 0, reverse=True)
        # organic_rank 在全表范围计算（真实声量名次），与 sov_rank 背离时说明排名靠推广撑起
        organic_rank_map = {
            r.get("name"): idx + 1
            for idx, r in enumerate(
                sorted(
                    (
                        r
                        for r in sov_all
                        if isinstance(r.get("organic_heat"), (int, float))
                    ),
                    key=lambda r: r.get("organic_heat"),
                    reverse=True,
                )
            )
        }
        sov_brief = [
            {
                "name": r.get("name"),
                "sov_rank": idx + 1,
                "share": r.get("share"),
                "sentiment": r.get("sentiment"),
                # organic_heat/promo_heat：真实竞争声量优先看 organic_heat（share=organic+promo
                # 会被推广拉高）；promo 显著高于 organic 时该品牌声量主要靠推广，下调采信
                "organic_heat": r.get("organic_heat"),
                "organic_rank": organic_rank_map.get(r.get("name")),
                "promo_heat": r.get("promo_heat"),
                # mentions：数据量风控——提及很少时名次靠后可能是数据稀疏，不可读成"弱"
                "mentions": r.get("mentions"),
                "role": r.get("role"),
            }
            for idx, r in enumerate(sov_sorted[:10])
        ]

        # 品牌组聚合 — 按母品牌族汇总声量份额（个体 sov 之上的组级视图；
        # organic/promo 拆分揭示族级真实声量 vs 推广占比）
        group_share_brief = [
            {
                "name": g.get("name"),
                "role": g.get("role"),
                "share": g.get("share"),
                "mentions": g.get("mentions"),
                "organic_heat": g.get("organic_heat"),
                "promo_heat": g.get("promo_heat"),
                "organic_sentiment": g.get("organic_sentiment"),
            }
            for g in (landscape.get("group_share") or [])[:10]
            if isinstance(g, dict)
        ]

        # Intent 层 — topic_radar (pains/gains/controversies) + unmet_needs + audiences
        intent = layers.get("intent") or {}
        # 未满足需求（已是 LLM 策展信号；只投分析字段，不带 post_ids/source_tasks 等运维字段）
        unmet_needs = [
            {
                "name": u.get("name"),
                "category": u.get("category"),
                "heat": u.get("heat"),
                "mentions": u.get("mentions"),
                "sentiment": u.get("sentiment"),
                "organic_sentiment": u.get("organic_sentiment"),
            }
            for u in (intent.get("unmet_needs") or [])
            if isinstance(u, dict)
        ]

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
            [
                c
                for c in (topic_radar.get("controversies") or [])
                if isinstance(c, dict)
            ],
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

        # 维度情感矩阵（压缩版）：仅 主体 + 竞品 × top6 维度，做细粒度逐属性竞争定位。
        # 整张矩阵 token 太贵，只截最相关行列；大盘切片（无 subject）跳过。
        drivers = foundation.get("drivers") or {}
        matrix_rows = drivers.get("entity_matrix") or []
        matrix_dims = [d for d in (drivers.get("dimensions_top") or []) if d][:6]
        focus_names = {n for n in ([subject] + (meta.get("competitors") or [])) if n}
        matrix_brief = []
        if matrix_rows and matrix_dims and focus_names:
            for row in matrix_rows:
                if not isinstance(row, dict) or row.get("entity") not in focus_names:
                    continue
                cells = row.get("dimensions") or {}
                dim_vals = {
                    d: {
                        "sentiment": cells[d].get("sentiment"),
                        "mentions": cells[d].get("mentions"),
                    }
                    for d in matrix_dims
                    if isinstance(cells.get(d), dict)
                    and cells[d].get("sentiment") is not None
                }
                if dim_vals:
                    matrix_brief.append(
                        {"entity": row.get("entity"), "dimensions": dim_vals}
                    )

        ref_name = (
            slice_refs[i].get("name") if slice_refs and i < len(slice_refs) else None
        )
        slice_label = (ref_name or "").strip()
        part: dict[str, Any] = {
            "slice_index": i,
            "_source_label": (
                f"Social Slice #{i}: {slice_label}"
                if slice_label
                else f"Social Slice #{i}"
            ),
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
        if group_share_brief:
            part["group_share"] = group_share_brief
        if matrix_brief:
            part["entity_dimension_matrix"] = matrix_brief
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

    news_media_section = _format_news_media_section(news_slices or [], news_slice_refs)

    coverage_signals = format_coverage_signals(coverage_check_result)

    return {
        "brief_section": brief_section,
        "research_context_section": research_context_section,
        "coverage_signals": coverage_signals,
        "slice_data": slice_data,
        "research_findings": research_findings,
        "news_media_section": news_media_section,
        "landscape_context_section": "",  # full_strategy 时由 service 层覆盖
    }


def parse_insight_response(response_text: str) -> dict[str, Any]:
    """解析 Insight (洞察层) LLM 输出"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Insight JSON 解析失败: %s...", text[:200])
        return {"social_tensions": [], "brand_opportunities": []}

    # 确保字段存在
    if "social_tensions" not in result:
        result["social_tensions"] = []
    if "brand_opportunities" not in result:
        result["brand_opportunities"] = []

    return result
