"""Strategy Market Report — Landscape Chain (竞争格局)

market_report 三层分析的**第 2 层**：agenda_map → landscape → strategic_brief。
基于 agenda_map 层（媒体议程图）+ 新闻切片原始数据，full_strategy 下还交叉社媒大盘的消费者侧
竞争信号，输出：媒体视角下的竞争格局、玩家定位、媒介声量对比、话语战场的胜负与动向，并**客观
校验**媒体声量是否反映消费者真实口碑（一致则确认、背离则分向标注，不预设找问题）。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section             : Brand Brief
- research_context_section  : 研究问题 + 需求理解
- agenda_map_section        : 上游 agenda_map 层的媒体议程图结果（必需，provides narrative backbone）
- news_slice_data           : 新闻切片原始 insight（媒体侧：entity/sentiment/SOV/themes/timeseries）
- social_dapan_section      : 社媒大盘切片的消费者侧投影（仅 full_strategy：各品牌 organic_heat /
                              promo_heat / organic_sentiment + group_share + overview，均为切片已有字段；
                              market_report / 无社媒大盘则降级为媒体纯）
- research_findings         : Research Agent 行业研究发现（自动注入）

## 输出结构

players             : 玩家名单 + media_sov + media_sentiment + narrative_position
                      + 消费者侧（consumer_standing / consumer_organic_sentiment）
positioning_map     : 二维定位图（媒体叙事轴，axes + positions）
discourse_battles   : 话语战场——谁在主导、谁在挑战
market_dynamics     : 动量变化（gainers / losers / structural_shifts）+ 媒体 vs 消费者一致性校验（背离则标注）

## 关键设计决策

1. **强制区分 target / competitor / context**。NewsSlice.entities.role 已标注，
   LLM 不得自行改判，否则会污染 SOV 计算。
2. **定位轴由 LLM 从 narrative_map 提炼**。轴语义必须能从 agenda_map 主导叙事的
   framing 抽象出来（如"科学实证 vs 营销故事化"），**禁止使用市场份额/营收等市场现实
   数据作为轴定义**——positioning_map 是「媒体叙事空间」的定位图，不是真实市场份额图。
3. **positioning_map 仅放有媒体覆盖的玩家**（source_count > 0）。0-source 玩家
   在媒体上失声本身已是 attention_gap 信号，不应被 LLM 用 industry_research 数据强行
   定位到象限里——那属于幻觉而非分析。
4. **discourse_battle 必须绑定 agenda_map 层的 agenda_battle**。防止 landscape 层自行
   幻觉出 agenda_map 层没有识别的战场。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """你是资深市场竞争情报分析师，擅长从媒体报道中还原竞争格局与品牌定位。

## 任务
在 agenda_map 层产出的"媒体议程图"基础上，进一步分析：
媒体视角下的竞争玩家、声量结构、定位差异、话语战场胜负。

## 核心分析框架

1. **Players（玩家）**：识别所有被媒体报道的实体，区分 target（研究主体）、
   competitor（直接竞品）、context（背景参与者，如监管/行业协会/分析机构）。
   full_strategy 下，每个 player 还要与社媒大盘做消费者侧交叉（见下「媒体 × 消费者 跨源交叉」节），
   揭示媒体声量是否反映真实口碑。
2. **Positioning Map（定位图，严格基于媒体叙事）**：由 LLM 根据 agenda_map.narrative_map
   的主导叙事 / framing 选择两个最有解释力的**语义轴**（如"科学实证 vs 营销故事化"、
   "权威 tier1 共识 vs tier3/wechat_mp 长尾"、"行业领导叙事 vs 挑战者叙事"），把主要玩家
   放上去，并给出每个位置的理由。
   **严格约束**：
   - X/Y 轴语义**必须能从 narrative_map 的 framing / theme 提炼**，禁止使用市场份额、
     营收、增长率等"市场现实"数据作为轴定义——positioning_map 是**媒体叙事空间**的定位图，
     不是真实市场份额图
   - positions **仅包含 source_count > 0 的玩家**（在本次 news 样本中有实际媒体报道）。
     brief 列出但 0-source 的竞品**不放上图**——它们在媒体上失声本身已经是 attention_gap
     信号，强行用 industry_research / 通用品类知识把它们定位到象限里属于幻觉
   - 每个 position 的 rationale **必须引用具体的媒体证据**（narrative theme / quote /
     tier 来源），禁止用 industry_research 的市场份额数字作为定位依据
3. **Discourse Battles（话语战场）**：agenda_map 识别的 agenda_battles 中，
   哪些玩家站在哪一方？是否存在话语权转移的迹象？
4. **Market Dynamics（动态）**：媒体覆盖度与情感的变化趋势，推断声量上扬/下滑的玩家，
   以及可能的结构性变化（如新进入者/技术切换/监管收紧）。

## 输出格式（严格 JSON，无 markdown）

{{
  "competitive_summary": "1-2 句概括竞争形态（点到为止、不堆数字）：有社媒大盘数据时，开头一句给媒体 vs 消费者交叉的核心判断（谁媒体主导/谁消费者真领先，一致或背离），再一句媒体侧形态；无社媒数据则仅述媒体侧",
  "players": [
    {{
      "name": "玩家名",
      "role": "target|competitor|context",
      "media_sov_pct": <float, 0-100, 在本次新闻样本中的声量占比>,
      "media_sentiment": <-2~2 加权>,
      "source_count": <int, 不同来源数>,
      "consumer_standing": "<str|null, 该玩家消费者侧的真实地位（一句话）；无社媒大盘数据填 null>",
      "consumer_organic_sentiment": <float|null, 该玩家社媒 organic_sentiment（剔除推广后的真实情感）；无社媒大盘数据填 null>,
      "narrative_position": "该玩家在媒体叙事中的主要定位（一句话）",
      "key_claims": ["媒体围绕该玩家的代表性论述"],
      "representative_voices": [
        {{"quote": "key_quotes 字面引用", "speaker": "key_quote.speaker（无则空）", "source": "key_quote.source_name", "source_tier": "tier1/tier2/tier3/wechat_mp"}}
      ]
    }}
  ],
  "positioning_map": {{
    "x_axis": {{"label": "X 轴标签", "low": "低端一侧语义", "high": "高端一侧语义"}},
    "y_axis": {{"label": "Y 轴标签", "low": "低端一侧语义", "high": "高端一侧语义"}},
    "rationale": "为何选择这两条轴作为最具解释力的定位维度",
    "positions": [
      {{
        "player": "玩家名",
        "x": <float, -1~1>,
        "y": <float, -1~1>,
        "rationale": "定位到该象限的证据"
      }}
    ]
  }},
  "discourse_battles": [
    {{
      "battle": "关联 agenda_map 的 contested_topic",
      "leaders": [{{"player": "...", "stance": "..."}}],
      "challengers": [{{"player": "...", "stance": "..."}}],
      "shift_direction": "momentum 方向：向 leaders / 向 challengers / stable",
      "evidence": "支持该判断的关键证据"
    }}
  ],
  "market_dynamics": {{
    "momentum_gainers": [
      {{"player": "...", "signal": "媒体报道正在增加的信号"}}
    ],
    "momentum_losers": [
      {{"player": "...", "signal": "媒体报道正在衰减的信号"}}
    ],
    "structural_shifts": [
      {{"shift": "结构性变化描述", "implication": "对竞争格局的含义"}}
    ]
  }}
}}

## 要求
- players: 3-10 个，按 media_sov_pct 降序，必须包含至少 1 个 target + 2 个 competitor
- positioning_map.positions: 数量按"严格约束"中的 source_count > 0 规则筛选后而定，可少于 players；
  若样本里有报道的玩家不足 2 个（无法构成"格局"），输出空 positions 数组而非强行编造
- discourse_battles: 条目必须能在 agenda_map 的 agenda_battles 里找到对应（禁止凭空杜撰）
- 若某字段无数据支持，使用空数组而非伪造内容
- momentum 判断需基于 `descriptive.coverage_timeseries` / `descriptive.sentiment_timeseries` 真实时序，
  以及 `event_clusters` 的 `tier_weighted_score` 与 `peak_date` 分布；禁止"感觉上升"
- `themes`（议题层）= 媒体反复讨论的抽象维度 + 态度（情感量纲 [-2,2]）：`sentiment_avg` 极化或
  `sentiment_weighted_by_tier` 分层冲突的议题是 **discourse_battles** 的直接来源；议题整体情感方向
  辅助判断 market_dynamics 走势。与 `event_clusters`（具体事件）正交，结合使用

## representative_voices 来源约束

`players[].representative_voices` 必须从输入 `key_quotes` 数组逐字选取
（quote/speaker/source/source_tier 按对应 key_quote 字段填），每个 player 0-2 条；
该玩家无合适 quote 时输出空数组。命名与 agenda_map 同名同 schema。

## 媒体 × 消费者 跨源交叉（社媒大盘 · 仅 full_strategy 提供）

竞争格局是多源综合：媒体侧来自新闻切片（media_sov / media_sentiment），消费者侧来自 `社媒大盘切片` 段
（**仅当非空时使用**；降级提示时所有 consumer_* 填 null）。社媒大盘提供各品牌的消费者侧真实数据，
**均为切片已有字段，不要另造任何派生变量**：
- `organic_heat`（自然声量）：品牌真实消费者声量，**用于排序**（不是百分比）。
- `promo_heat`（推广声量）、`organic_sentiment`（剔除推广后的真实情感）、`group_share`（母品牌族聚合的 organic/promo，
  子品牌可看族级真实地位）、`overview`（品类整体自然/推广总量）。
  （逐维度口碑细节归 Insight 深挖，landscape 只看逐品牌的声量/情感位置。）

用法（按品牌名跨渠道对齐；**不改 positioning_map 的媒体叙事轴**）：
0. **数据用来"垫"判断，不要全倒进输出**：organic_heat 排序、organic_sentiment 是你得出结论的依据，
   但输出字段要**蒸馏成最关键的判断**，不堆砌一串数字。
1. 给每个 player 填 `consumer_standing`：**一句话、punchy** 给该玩家最关键的消费者侧判断，**不罗列数字与多维度**；
   `consumer_organic_sentiment` 取该品牌 organic_sentiment。社媒大盘有该品牌则填，无则均 null。
2. 媒体声量（media_sov）与消费者真实声量（organic_heat）**口径不同，只比相对排序、不比百分比**
   （媒体样本 vs 社媒样本、竞品集合 vs 全实体）。**`competitive_summary` 开头一句先给两侧交叉的核心判断**
   （谁媒体主导、谁消费者真领先，一致还是背离——**点到为止、不堆数字**），避免被 media_sov 排序的 roster
   盖住；再简述媒体侧形态。**结论由数据自行得出，不预设、不夸大、不硬找问题**。
3. **数据量风控（重要）**：某品牌社媒 `mentions` 很少时，其 `organic_heat` 排序靠后**很可能是数据稀疏**
   （采集去重的"首见原则"会把同时提及本品+竞品的原文优先归本品，系统性低估竞品）——**不得据此判其
   "消费者弱"**；应 hedging 或注明"该竞品社媒样本小，真实口碑可能优于数据所呈现"。
4. positioning_map 仍只用媒体叙事轴；消费者数据仅用于校验媒体定位是否反映真实竞争，不重定义轴、不挪动位置。

## 切片溯源规范（重要）

`players[].rationale` / `discourse_battles[].evidence` 等说理性字段，引用切片层数据时
应在文字中点明对应**切片标签**——格式 `News Slice #<i>: <slice_name>`，取每个切片对象内
`_source_label` 字段值。例如：`"该结论基于 <取自切片 _source_label> 中竞品 SOV 数据"`。
**禁止**只写"切片数据"等模糊形式。

## 禁止行为
- 禁止改判 NewsSlice.entities.role（target/competitor/context 以输入为准）
- 禁止脱离 agenda_map 议程图单独产生新的 battle
- 禁止在 representative_voices 中编造未出现的原文
- 禁止使用 `result_data.page_synthesis`（briefing / event_titles 是 LLM 散文，仅供 slice 页面阅读，不作策略输入）

## 行业研究数据（research_findings）使用指南
- 行业研究数据来自自动化搜索引擎 + 行业报告 + 公开数据的综合分析，代表**专家/行业视角**
- 研究数据中的量化数据点（市场份额、增长率等）可用于校验 media_sov 与实际市场地位的偏差
- 如 `{{research_findings}}` 段落为空，**正常忽略**该部分，players / positioning_map / discourse_battles 只基于 agenda_map 和新闻切片
- **使用边界**：可在 market_dynamics.structural_shifts 中引用研究数据作为行业趋势佐证；
  但 positioning_map / players 的定位**不能基于研究数据**——这两个字段是「媒体如何定位竞争」
  的产物，不是「市场实际如何分布」的产物
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{research_findings}

## 媒体议程图 (Agenda Map) 结果

{agenda_map_section}

## 新闻切片原始数据

{news_slice_data}

## 社媒大盘切片（消费者侧 · 仅 full_strategy）

{social_dapan_section}"""


def create_landscape_chain() -> Runnable:
    """创建 Landscape (竞争格局) LLM 链 — market_report 三层第 2 层"""
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


def _format_news_slices_for_landscape(
    news_slices: list[dict],
    news_slice_refs: list[dict] | None = None,
) -> str:
    """将 NewsSlice 数据格式化为 Landscape 层输入（ADR-003 新 schema）。

    重点字段：entities（含 role / by_tier sentiment）+ competitive（players + quote_share）+
    media_landscape + 时序（用于 momentum 判断）。

    `news_slice_refs` 与 news_slices 同序，用于在每个切片对象注入 `_source_label`
    （`News Slice #i: <name>`），让 LLM 在 evidence 字段中以稳定标签引用切片。
    """
    if not news_slices:
        return "（无新闻切片数据）"

    parts: list[dict[str, Any]] = []
    for idx, ns in enumerate(news_slices):
        rd = ns.get("result_data")
        if not rd or isinstance(rd, str):
            continue
        descriptive = rd.get("descriptive") or {}
        media_landscape = rd.get("media_landscape") or {}
        competitive = rd.get("competitive") or {}

        ref_name = (
            news_slice_refs[idx].get("name")
            if news_slice_refs and idx < len(news_slice_refs)
            else None
        )
        slice_label = (ref_name or ns.get("name") or "").strip()
        parts.append(
            {
                "_source_label": (
                    f"News Slice #{idx}: {slice_label}"
                    if slice_label
                    else f"News Slice #{idx}"
                ),
                "slice_name": ns.get("name", ""),
                "article_count": descriptive.get("articles_filtered", 0),
                "source_tier_distribution": descriptive.get("source_tier_distribution"),
                "sentiment_overall": descriptive.get("sentiment_overall"),
                "sentiment_by_tier": descriptive.get("sentiment_by_tier"),
                # 时序信号（最近 30 个时间点），供 momentum 判断
                "coverage_timeseries": (descriptive.get("coverage_timeseries") or [])[
                    -30:
                ],
                "sentiment_timeseries": (descriptive.get("sentiment_timeseries") or [])[
                    -30:
                ],
                "media_landscape": {
                    "source_pyramid": media_landscape.get("source_pyramid"),
                    "top_sources": media_landscape.get("top_sources"),
                },
                "entities": [
                    {
                        "name": e.get("name"),
                        "role": e.get("role"),
                        "mention_count": e.get("mention_count"),
                        "source_count": e.get("source_count"),
                        "cross_task_count": e.get("cross_task_count"),
                        "sentiment_avg": e.get("sentiment_avg"),
                        "sentiment_weighted_by_tier": e.get(
                            "sentiment_weighted_by_tier"
                        ),
                        "sentiment_by_tier": e.get("sentiment_by_tier"),
                    }
                    for e in (rd.get("entities") or [])[:15]
                    if isinstance(e, dict)
                ],
                "competitive": {
                    "players": competitive.get("players"),
                    "quote_share": competitive.get("quote_share"),
                },
                "event_clusters_summary": [
                    {
                        "cluster_id": c.get("cluster_id"),
                        "article_count": c.get("article_count"),
                        "first_reported_at": c.get("first_reported_at"),
                        "peak_date": c.get("peak_date"),
                        "tier_weighted_score": c.get("tier_weighted_score"),
                    }
                    for c in (rd.get("event_clusters") or [])[:8]
                    if isinstance(c, dict)
                ],
                "themes": [
                    {
                        "name": t.get("name"),
                        "article_count": t.get("article_count"),
                        "sentiment_avg": t.get("sentiment_avg"),
                        "sentiment_weighted_by_tier": t.get(
                            "sentiment_weighted_by_tier"
                        ),
                        "tier_weighted_score": t.get("tier_weighted_score"),
                    }
                    for t in (rd.get("themes") or [])[:8]
                    if isinstance(t, dict)
                ],
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
            }
        )

    if not parts:
        return "（新闻切片数据均无有效 insight 结果）"
    return json.dumps(parts, ensure_ascii=False, indent=2)


def _format_agenda_map_section(agenda_map_result: dict | None) -> str:
    """将 agenda_map 结果精简为 landscape 层输入。"""
    if not agenda_map_result:
        return "（agenda_map 未生成）"
    condensed = {
        "media_landscape_summary": agenda_map_result.get("media_landscape_summary"),
        "narrative_map": [
            {
                "theme": n.get("theme"),
                "framing": n.get("framing"),
                "sentiment": n.get("sentiment"),
                "heat_rank": n.get("heat_rank"),
                "credibility": n.get("credibility"),
                "representative_voices": [
                    {"quote": v.get("quote"), "source_tier": v.get("source_tier")}
                    for v in (n.get("representative_voices") or [])[:2]
                ],
            }
            for n in (agenda_map_result.get("narrative_map") or [])
        ],
        "agenda_battles": agenda_map_result.get("agenda_battles") or [],
        "attention_gaps": agenda_map_result.get("attention_gaps") or [],
    }
    return json.dumps(condensed, ensure_ascii=False, indent=2)


def _format_social_dapan_for_landscape(dapan: dict | None) -> str:
    """社媒大盘切片的消费者侧【竞争】投影（仅 full_strategy 注入）。

    只取竞争 roster 维度，供媒体 × 消费者多源交叉。投影**切片已有的结构化字段**（不碰散文报告、
    不派生新变量）：sov_ranking（各品牌 organic_heat / promo_heat / organic_sentiment）+ group_share
    （母品牌族）+ overview（自然/推广总量）。
    **不含消费者话题**——"消费者在谈什么"归 Agenda Map（attention_gaps）/ Insight，不进竞争 roster。
    无数据时返回降级提示，LLM 据此保持媒体纯。
    """
    if not dapan or not isinstance(dapan, dict):
        return "（无社媒大盘数据：本次为纯媒体视角，players 的 consumer_* 字段一律填 null）"
    layers = dapan.get("layers") or {}
    landscape = layers.get("landscape") or {}
    overview = landscape.get("overview") or {}

    def _brand(r: dict) -> dict:
        # 只投影切片已有的一二阶字段，不派生新变量。mentions 用于判断数据量是否充分
        # （竞品社媒讨论稀疏时不能读成"消费者弱"，见跨源交叉节的数据风控）
        return {
            "name": r.get("name"),
            "role": str(r.get("role") or "").lower(),
            "organic_heat": r.get("organic_heat"),
            "promo_heat": r.get("promo_heat"),
            "organic_sentiment": r.get("organic_sentiment"),
            "sentiment": r.get("sentiment"),
            "mentions": r.get("mentions"),
        }

    proj = {
        "overview": {
            "total_organic_heat": overview.get("total_organic_heat"),
            "total_promo_heat": overview.get("total_promo_heat"),
        },
        "sov_ranking": [
            _brand(r)
            for r in (landscape.get("sov_ranking") or [])[:12]
            if isinstance(r, dict) and r.get("name")
        ],
        "group_share": [
            {
                "name": g.get("name"),
                "role": str(g.get("role") or "").lower(),
                "organic_heat": g.get("organic_heat"),
                "promo_heat": g.get("promo_heat"),
            }
            for g in (landscape.get("group_share") or [])[:10]
            if isinstance(g, dict) and g.get("name")
        ],
    }
    # 注：逐维度心智（entity_dimension_matrix）属"消费者深挖"的深度，归 Insight（已在用，
    # 且散文有篇幅）；landscape 是可扫读的竞争 roster，只用逐品牌指标，避免把卡片堆散。

    return json.dumps(proj, ensure_ascii=False, indent=2)


def format_inputs_for_landscape(
    agenda_map_result: dict | None,
    news_slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slice_refs: list[dict] | None = None,
    research_findings: str = "",
    social_dapan: dict | None = None,
) -> dict[str, Any]:
    """构建 Landscape chain 的输入参数字典。

    `news_slice_refs` 与 news_slices 同序的 [{id, name}] 列表，用于让 LLM 在
    evidence 字段中以 `News Slice #<i>: <name>` 形式精准引用。
    `social_dapan`：social 大盘切片的 result_data（仅 full_strategy），投影为消费者侧
    结构化数据，与新闻切片一起做媒体 × 消费者多源竞争交叉。
    """
    brief_section = ""
    if brief:
        brief_section = (
            f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        )

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "research_findings": research_findings,
        "agenda_map_section": _format_agenda_map_section(agenda_map_result),
        "news_slice_data": _format_news_slices_for_landscape(
            news_slices, news_slice_refs
        ),
        "social_dapan_section": _format_social_dapan_for_landscape(social_dapan),
    }


def parse_landscape_response(response_text: str) -> dict[str, Any]:
    """解析 Landscape LLM 输出。"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Landscape JSON 解析失败: %s...", text[:200])
        return {
            "competitive_summary": "",
            "players": [],
            "positioning_map": {},
            "discourse_battles": [],
            "market_dynamics": {},
        }

    result.setdefault("competitive_summary", "")
    result.setdefault("players", [])
    result.setdefault("positioning_map", {})
    result.setdefault("discourse_battles", [])
    result.setdefault("market_dynamics", {})

    return result
