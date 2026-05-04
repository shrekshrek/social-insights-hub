"""Strategy Market Report — Landscape Chain (竞争格局)

market_report 三层分析的**第 2 层**：agenda_map → landscape → strategic_brief。
基于 agenda_map 层（媒体议程图）+ 新闻切片原始数据，输出：
媒体视角下的竞争格局、玩家定位、媒介声量对比、话语战场的胜负与动向。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section             : Brand Brief
- research_context_section  : 研究问题 + 需求理解
- agenda_map_section        : 上游 agenda_map 层的媒体议程图结果（必需，provides narrative backbone）
- news_slice_data           : 新闻切片原始 insight（提供 entity/sentiment/SOV 数据）
- research_findings         : Research Agent 行业研究发现（自动注入）

## 输出结构

players             : 玩家名单 + media_sov + media_sentiment + narrative_position
positioning_map     : 二维定位图（axes + positions）
discourse_battles   : 话语战场——谁在主导、谁在挑战
market_dynamics     : 动量变化（gainers / losers / structural_shifts）

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
  "competitive_summary": "一句话概括当前媒体视角下的竞争形态",
  "players": [
    {{
      "name": "玩家名",
      "role": "target|competitor|context",
      "media_sov_pct": <float, 0-100, 在本次新闻样本中的声量占比>,
      "media_sentiment": <-2~2 加权>,
      "source_count": <int, 不同来源数>,
      "narrative_position": "该玩家在媒体叙事中的主要定位（一句话）",
      "key_claims": ["媒体围绕该玩家的代表性论述"],
      "evidence_quote": {{"quote": "原文", "source": "来源", "source_tier": "tier1/tier2/tier3/wechat_mp"}}
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
- positioning_map.positions: **仅包含 source_count > 0 的玩家**（在本次 news 样本里有实际媒体报道），
  数量按实际可定位玩家而定，可少于 players（0-source 玩家不放上图）。若样本里实际有报道的玩家
  少于 2 个（无法构成"格局"），输出空 positions 数组而非强行编造
- discourse_battles: 条目必须能在 agenda_map 的 agenda_battles 里找到对应（禁止凭空杜撰）
- 若某字段无数据支持，使用空数组而非伪造内容
- momentum 判断需基于 `descriptive.coverage_timeseries` / `descriptive.sentiment_timeseries` 真实时序，
  以及 `event_clusters` 的 `tier_weighted_score` 与 `peak_date` 分布；禁止"感觉上升"

## 禁止行为
- 禁止改判 NewsSlice.entities.role（target/competitor/context 以输入为准）
- 禁止脱离 agenda_map 议程图单独产生新的 battle
- 禁止在 evidence_quote 中编造未出现的原文
- 禁止使用 `result_data.page_synthesis`（briefing / event_titles 是 LLM 散文，仅供 slice 页面阅读，不作策略输入）
- **禁止用 industry_research 的市场份额 / 营收 / 增长率数据**作为 positioning_map 的轴定义或玩家坐标依据
- **禁止把 source_count=0 的玩家放进 positioning_map.positions**（无媒体覆盖即无媒体定位可言）

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

{news_slice_data}"""


def create_landscape_chain() -> Runnable:
    """创建 Landscape (竞争格局) LLM 链 — market_report 三层第 2 层"""
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


def _format_news_slices_for_landscape(news_slices: list[dict]) -> str:
    """将 NewsSlice 数据格式化为 Landscape 层输入（ADR-003 新 schema）。

    重点字段：entities（含 role / by_tier sentiment）+ competitive（players + quote_share）+
    media_landscape + 时序（用于 momentum 判断）。
    """
    if not news_slices:
        return "（无新闻切片数据）"

    parts: list[dict[str, Any]] = []
    for ns in news_slices:
        rd = ns.get("result_data")
        if not rd or isinstance(rd, str):
            continue
        descriptive = rd.get("descriptive") or {}
        media_landscape = rd.get("media_landscape") or {}
        competitive = rd.get("competitive") or {}

        parts.append({
            "slice_name": ns.get("name", ""),
            "article_count": descriptive.get("articles_filtered", 0),
            "source_tier_distribution": descriptive.get("source_tier_distribution"),
            "sentiment_overall": descriptive.get("sentiment_overall"),
            "sentiment_by_tier": descriptive.get("sentiment_by_tier"),
            # 时序信号（最近 30 个时间点），供 momentum 判断
            "coverage_timeseries": (descriptive.get("coverage_timeseries") or [])[-30:],
            "sentiment_timeseries": (descriptive.get("sentiment_timeseries") or [])[-30:],
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
                    "sentiment_weighted_by_tier": e.get("sentiment_weighted_by_tier"),
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
            "key_quotes": [
                {
                    "speaker": q.get("speaker"),
                    "speaker_role": q.get("speaker_role"),
                    "quote": q.get("quote"),
                    "source_name": q.get("source_name"),
                    "source_tier": q.get("source_tier"),
                }
                for q in (rd.get("quotes") or [])[:6]
                if q.get("speaker_role") in ("official", "executive", "analyst")
            ],
        })

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


def format_inputs_for_landscape(
    agenda_map_result: dict | None,
    news_slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    research_findings: str = "",
) -> dict[str, Any]:
    """构建 Landscape chain 的输入参数字典。"""
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "research_findings": research_findings,
        "agenda_map_section": _format_agenda_map_section(agenda_map_result),
        "news_slice_data": _format_news_slices_for_landscape(news_slices),
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
