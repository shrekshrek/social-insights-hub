"""Strategy Market Report — Landscape Chain (竞争格局)

market_report 三层分析的**第 2 层**：agenda_map → landscape → strategic_brief。
基于 agenda_map 层（媒体议程图）+ 新闻切片原始数据，输出：
媒体视角下的竞争格局、玩家定位、媒介声量对比、话语战场的胜负与动向。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section             : Brand Brief
- research_context_section  : 研究问题 + 需求理解
- agenda_map_section        : 上游 agenda_map 层的媒体议程图结果（必需，provides narrative backbone）
- news_slice_data           : 新闻切片原始 insight（提供 entity/sentiment/SOV 数据）
- market_context            : 知识库 RAG 背景（可选）

## 输出结构

players             : 玩家名单 + media_sov + media_sentiment + narrative_position
positioning_map     : 二维定位图（axes + positions）
discourse_battles   : 话语战场——谁在主导、谁在挑战
market_dynamics     : 动量变化（gainers / losers / structural_shifts）

## 关键设计决策

1. **强制区分 target / competitor / context**。NewsSlice.entities.role 已标注，
   LLM 不得自行改判，否则会污染 SOV 计算。
2. **定位轴由 LLM 在 brief 语境下生成**。不固定"价格/品质"这种预设轴，
   因为不同品类关注的张力不同，定位轴应反映实际讨论热点。
3. **discourse_battle 必须绑定 agenda_map 层的 agenda_battle**。防止 landscape 层自行
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
2. **Positioning Map（定位图）**：由 LLM 根据 agenda_map 的叙事热点选择两个最有解释力的
   语义轴（如"技术领导 vs 规模领导"），把主要玩家放上去，并给出每个位置的理由。
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
- positioning_map.positions: 3-6 个玩家，必须与 players 数组重合
- discourse_battles: 条目必须能在 agenda_map 的 agenda_battles 里找到对应（禁止凭空杜撰）
- 若某字段无数据支持，使用空数组而非伪造内容
- momentum 判断需基于 coverage.trend 或 narratives 数量变化，禁止"感觉上升"

## 禁止行为
- 禁止改判 NewsSlice.entities.role（target/competitor/context 以输入为准）
- 禁止脱离 agenda_map 议程图单独产生新的 battle
- 禁止在 evidence_quote 中编造未出现的原文

## 市场背景数据（market_context）使用指南
- 知识库内容以宏观互联网/经济/政策统计为主，可能与本次研究主题不直接相关
- 如 `{{market_context}}` 段落为空或内容与 brief 主题无明显关联，**必须忽略**该部分，players / positioning_map / discourse_battles 只基于 agenda_map 和新闻切片
- 仅当知识库内容与研究主题直接相关时，才可在 market_dynamics.structural_shifts 中作为宏观参照引用
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{market_context}

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
    """将 NewsSlice 数据格式化为 Landscape 层输入，重点提取 entities + competitive_landscape。"""
    if not news_slices:
        return "（无新闻切片数据）"

    parts: list[dict[str, Any]] = []
    for ns in news_slices:
        rd = ns.get("result_data")
        if not rd or isinstance(rd, str) or rd.get("error"):
            continue
        stats = ns.get("stats") or {}
        parts.append({
            "slice_name": ns.get("name", ""),
            "article_count": stats.get("articles_total", 0),
            "source_tier_distribution": stats.get("source_tier_distribution"),
            "coverage_trend": (rd.get("coverage") or {}).get("trend"),
            "entities": [
                {
                    "name": e.get("name"),
                    "role": e.get("role"),
                    "mention_count": e.get("mention_count"),
                    "sentiment": e.get("sentiment"),
                    "source_count": e.get("source_count"),
                    "key_claims": (e.get("key_claims") or [])[:3],
                }
                for e in (rd.get("entities") or [])[:15]
                if isinstance(e, dict)
            ],
            "competitive_landscape": rd.get("competitive_landscape"),
            "narratives_headlines": [
                {"theme": n.get("theme"), "article_count": n.get("article_count")}
                for n in (rd.get("narratives") or [])[:5]
                if isinstance(n, dict)
            ],
            "key_quotes": (rd.get("key_quotes") or [])[:4],
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
    market_context: str = "",
) -> dict[str, Any]:
    """构建 Landscape chain 的输入参数字典。"""
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "market_context": market_context or "",
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
