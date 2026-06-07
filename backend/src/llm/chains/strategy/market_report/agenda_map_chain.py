"""Strategy Market Report — Agenda Map Chain (媒体议程图)

market_report 三层分析的**第 1 层**：agenda_map → landscape → strategic_brief。
从新闻切片数据中提炼：媒体如何定义和包装该品类/议题，有哪些主导叙事，
哪些是被媒体争夺的话语战场，哪些是值得关注的注意力盲区。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section       : Brand Brief（主体 + 分析目标）
- research_context_section : 研究问题 + 需求理解
- coverage_signals    : 跨切片数据质量诊断（warnings + data_highlights），来自
                        strategy.coverage_check_result，用于校准结论置信度
- news_slice_data     : 所有 NewsSlice 的 insight 数据聚合（coverage/narratives/entities/key_quotes）
- research_findings   : Research Agent 行业研究发现（自动注入）

## 输出结构

narrative_map        : 媒体主导叙事及其 framing 和代表声音
agenda_battles       : 存在 tier1/tier2 分歧或正反争议的议题
media_voice_patterns : 按 source_tier 聚合的声音模式
attention_gaps       : 值得报道但当前报道稀缺的议题

## 关键设计决策

1. **不输出消费者 tension**。Agenda Map 层的视角严格限定在"媒体如何定义议题"，
   consumer voice 不是该路径的主源，若需人群反应应走 brand_strategy 路径。
2. **强调 tier 对比**。narrative 的置信度依赖 tier1/tier2 是否达成共识，
   仅依赖 wechat_mp 的声音必须标注为 "emerging / unverified"。
3. **模型选用 chat**。insight 级别输出，不需要 reasoner 的长链推理。
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


SYSTEM_TEMPLATE = """你是资深媒体战略分析师，擅长解读媒体议程（media agenda）与话语结构（discourse）。

## 任务
基于提供的新闻媒体切片数据（NewsSlice insight），输出"媒体议程图"：
媒体当前如何定义、包装、竞争这个品类/议题，主导叙事是什么，存在哪些被争夺的话语战场，
哪些是值得被报道却明显缺位的议题。

## 核心分析框架

> 输入里的 `themes`（议题层）是已聚合的"媒体反复讨论的抽象维度 + 态度 + tier 加权热度"，
> 是识别 narrative / battle / pattern 的一手信号：`tier_weighted_score` 高 = 主导叙事候选；
> `sentiment_avg` 极化（正负分明）或 `sentiment_by_tier` 分层冲突 = agenda_battle 候选。
> 注意 themes 情感量纲为 [-2,2]。themes 与 `event_clusters`（具体事件）正交，二者结合使用。

1. **Narrative Map（叙事地图）**：识别媒体正在推进的主导叙事（narratives），
   每条叙事必须说明 framing（媒体如何定义问题），supporting_sources（由哪类来源支撑），
   representative_voices（引用具体 quote + 来源）。
2. **Agenda Battles（议题战场）**：存在 tier 之间分歧或正反争论的议题。
   同一议题若 tier1 权威央媒与 tier2 行业门户观点分化，或情感分布严重撕裂，属于 battle。
3. **Media Voice Patterns（声音模式）**：按 source_tier 分层归纳——
   - authoritative_consensus: tier1 达成共识的议题
   - industry_debate: tier2 内部存在分歧的议题
   - emerging_narratives: 主要来自 wechat_mp / tier3 的新兴声音（标注 unverified）
4. **Attention Gaps（注意力盲区）**：业务层面重要、但当前媒体报道稀缺的议题。
   需结合 brand_brief / research_questions 判断"重要"的标准。

## 输出格式（严格 JSON，无 markdown）

{{
  "media_landscape_summary": "一句话总结当前媒体议程的整体形态",
  "narrative_map": [
    {{
      "theme": "叙事主题",
      "framing": "媒体如何定义该议题（一句话）",
      "sentiment": <-2~2 加权>,
      "heat_rank": <int, 1 = 最强>,
      "supporting_sources": {{"tier1": <int>, "tier2": <int>, "tier3": <int>, "wechat_mp": <int>}},
      "representative_voices": [
        {{"quote": "key_quotes 字面引用", "speaker": "key_quote.speaker（无则空）", "source": "key_quote.source_name", "source_tier": "tier1/tier2/tier3/wechat_mp"}}
      ],
      "credibility": "high|medium|low",
      "cross_slice_evidence": ["<取自切片 _source_label>", "<取自切片 _source_label>"]
    }}
  ],
  "agenda_battles": [
    {{
      "contested_topic": "被争论的议题",
      "camps": [
        {{"stance": "立场A一句话", "supporting_tiers": ["tier1"], "sample_quotes": ["..."]}},
        {{"stance": "立场B一句话", "supporting_tiers": ["tier2", "wechat_mp"], "sample_quotes": ["..."]}}
      ],
      "implication": "该分歧对品牌/行业的含义"
    }}
  ],
  "media_voice_patterns": {{
    "authoritative_consensus": [
      {{"topic": "主题", "stance": "共识立场", "evidence": "tier1 的体现"}}
    ],
    "industry_debate": [
      {{"topic": "主题", "positions": ["立场1", "立场2"]}}
    ],
    "emerging_narratives": [
      {{"topic": "主题", "why_unverified": "为何需要留待主流媒体验证", "originating_tier": "wechat_mp"}}
    ]
  }},
  "attention_gaps": [
    {{
      "topic": "缺位议题",
      "why_matters": "为何该议题与 brand_brief 的分析目标相关",
      "risk_or_opportunity": "risk|opportunity"
    }}
  ]
}}

## 要求
- narrative_map: 3-5 条，按 heat_rank 升序
- agenda_battles: 0-3 条，仅在确实存在分歧时输出
- attention_gaps: 1-3 条，禁止输出"一切都已充分覆盖"这类空内容
- credibility=high 要求 tier1+tier2 共同支撑；仅 tier3/wechat_mp 支撑的 narrative 必须 low

## representative_voices 来源约束

`representative_voices` 必须从输入 `key_quotes` 数组逐字选取（quote/speaker/source/source_tier
按对应 key_quote 字段填）；找不到合适 quote 时输出空数组。

## 切片溯源规范（重要）

`narrative_map[].cross_slice_evidence` 必须填**News Slice 完整标签**，格式 `News Slice #<i>: <slice_name>`，
取每个切片对象内 `_source_label` 字段值。**禁止**只写切片名（如 `slice_name#1`）等模糊形式——
前端依赖这个标签反查上游切片。

`representative_voices[].source` 指**真实媒体来源**（key_quote.source_name 字段值），不是切片标签。两者语义不同，不要混用。

## 字段解读（NewsSlice 新 schema，仅消费结构化层）

- `descriptive.articles_filtered`: 切片实际参与分析的文章数（去重 + 过滤 low 后）
- `descriptive.source_tier_distribution`: 各 tier 的文章数量分布（媒介层级）
- `descriptive.sentiment_overall` / `sentiment_by_tier`: 整体情感（-2~2）+ 按 tier 分层情感（核心议程定调信号）
- `descriptive.cross_task_overlap`: 跨任务重叠分布（高重叠 = 多角度共同关注，强热度信号）
- `descriptive.coverage_timeseries` / `sentiment_timeseries`: 报道量与情感的时序，可用于判断议题阶段（上升/平稳/回落）
- `event_clusters`: 跨文章事件聚类（含 first_reported_at / peak_date / tier_weighted_score / in_task_ids），是议程的"事实级"载体——narrative_map 应基于这些 cluster 抽象出主题
- `entities`: 归一后实体（含 role / mention_count / source_count / sentiment_avg / sentiment_by_tier），可识别议程主角
- `quotes`: 已 speaker 分级的引述（official > executive > analyst > kol > other），含 article_id 锚点；`representative_voices` 优先选 official + executive
- `media_landscape.source_pyramid`: 4 层金字塔（tier × article_count × sentiment_avg × top_source_names），是 credibility 与议程位置判断依据
- `competitive`: 主体/竞品投影（players + quote_share），含跨 tier sentiment 与官方引述占比

**禁止使用**：result_data.page_synthesis（含 LLM 散文 briefing / event_titles，仅供 slice 页面阅读，不作策略输入）。

## 禁止行为
- 禁止虚构未出现在数据中的引述或来源
- 禁止把"消费者认为"作为论据——该路径只分析媒体视角，消费者声音走 brand_strategy 路径
- 禁止输出与 research_questions 无关的通用媒体观察

## 行业研究数据（research_findings）使用指南
- 行业研究数据来自自动化搜索引擎 + 行业报告 + 公开数据的综合分析，代表**专家/行业视角**
- **交叉验证**：研究数据反映行业实际趋势，可校验媒体叙事是否与行业现实一致——若出现偏差，即为高价值 attention_gap
- 研究数据中的置信度标记（high/medium/low）反映证据充分程度
- 如 `{{research_findings}}` 段落为空，**正常忽略**该部分，narrative_map / agenda_battles 只基于新闻切片数据
- 研究数据可在 attention_gaps 中作为行业事实参照引用
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{coverage_signals}

{research_findings}

## 新闻切片数据

{news_slice_data}"""


def create_agenda_map_chain() -> Runnable:
    """创建 Agenda Map (媒体议程图) LLM 链 — market_report 三层第 1 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_TEMPLATE),
            ("user", USER_TEMPLATE),
        ]
    )
    return prompt | llm


def _build_research_context_section(research_design: dict | None) -> str:
    """构建研究上下文段落：研究问题 + 需求理解"""
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


def _format_news_slices_for_agenda(
    news_slices: list[dict],
    news_slice_refs: list[dict] | None = None,
) -> str:
    """将 NewsSlice 数据格式化为 Agenda Map 层输入（ADR-003 新 schema）。

    只消费结构化层（descriptive / entities / quotes / event_clusters /
    media_landscape / competitive），不消费 page_synthesis。

    `news_slice_refs` 与 news_slices 同序，用于在每个切片对象注入 `_source_label`
    （`News Slice #i: <name>`），让 LLM 在 cross_slice_evidence / evidence 字段中
    精准引用切片，便于前端反查。
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
                "cross_task_overlap": (descriptive.get("cross_task_overlap") or {}).get(
                    "distribution"
                ),
                "coverage_timeseries": (descriptive.get("coverage_timeseries") or [])[
                    -30:
                ],  # 最多最近 30 个时间点
                "media_landscape": {
                    "source_pyramid": media_landscape.get("source_pyramid"),
                    "top_sources": media_landscape.get("top_sources"),
                },
                "event_clusters": [
                    {
                        "cluster_id": c.get("cluster_id"),
                        "article_count": c.get("article_count"),
                        "first_reported_at": c.get("first_reported_at"),
                        "peak_date": c.get("peak_date"),
                        "tier_weighted_score": c.get("tier_weighted_score"),
                        "first_reporter": c.get("first_reporter"),
                        "in_task_ids": c.get("in_task_ids"),
                    }
                    for c in (rd.get("event_clusters") or [])[:8]
                ],
                "themes": [
                    {
                        "name": t.get("name"),
                        "article_count": t.get("article_count"),
                        "source_count": t.get("source_count"),
                        "sentiment_avg": t.get("sentiment_avg"),
                        "sentiment_weighted_by_tier": t.get(
                            "sentiment_weighted_by_tier"
                        ),
                        "tier_weighted_score": t.get("tier_weighted_score"),
                    }
                    for t in (rd.get("themes") or [])[:8]
                    if isinstance(t, dict)
                ],
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
                    # 新闻切片 entities 上限 30（pass1_chain），取 [:15] 覆盖
                    # target+competitor+高 mention context；agenda_map 需看媒体讨论的全貌
                    for e in (rd.get("entities") or [])[:15]
                    if isinstance(e, dict)
                ],
                "key_quotes": [
                    {
                        "speaker": q.get("speaker"),
                        "speaker_role": q.get("speaker_role"),
                        "quote": q.get("quote"),
                        "source_name": q.get("source_name"),
                        "source_tier": q.get("source_tier"),
                        "context": q.get("context"),
                    }
                    # Pass 1 quotes 上限 12，取 [:12] = 全部高分级 quote
                    for q in (rd.get("quotes") or [])[:12]
                    if q.get("speaker_role") in ("official", "executive", "analyst")
                ],
                "competitive": {
                    "players": competitive.get("players"),
                    "quote_share": competitive.get("quote_share"),
                },
            }
        )

    if not parts:
        return "（新闻切片数据均无有效结构化结果）"
    return json.dumps(parts, ensure_ascii=False, indent=2)


def format_inputs_for_agenda_map(
    news_slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    news_slice_refs: list[dict] | None = None,
    research_findings: str = "",
    coverage_check_result: dict | None = None,
) -> dict[str, Any]:
    """构建 Agenda Map chain 的输入参数字典。

    `news_slice_refs` 与 news_slices 同序的 [{id, name}] 列表，用于让 LLM 在
    cross_slice_evidence 字段中以 `News Slice #<i>: <name>` 形式精准引用。
    """
    brief_section = ""
    if brief:
        brief_section = (
            f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        )

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "coverage_signals": format_coverage_signals(coverage_check_result),
        "research_findings": research_findings,
        "news_slice_data": _format_news_slices_for_agenda(news_slices, news_slice_refs),
    }


def parse_agenda_map_response(response_text: str) -> dict[str, Any]:
    """解析 Agenda Map LLM 输出（容错剥离 markdown fence）。"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error("Agenda Map JSON 解析失败: %s...", text[:200])
        return {
            "media_landscape_summary": "",
            "narrative_map": [],
            "agenda_battles": [],
            "media_voice_patterns": {},
            "attention_gaps": [],
        }

    # 兜底字段
    for key in (
        "narrative_map",
        "agenda_battles",
        "attention_gaps",
    ):
        result.setdefault(key, [])
    result.setdefault("media_voice_patterns", {})
    result.setdefault("media_landscape_summary", "")

    return result
