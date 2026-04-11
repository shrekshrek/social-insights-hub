"""Strategy Market Report — Agenda Map Chain (媒体议程图)

market_report 三层分析的**第 1 层**：agenda_map → landscape → strategic_brief。
从新闻切片数据中提炼：媒体如何定义和包装该品类/议题，有哪些主导叙事，
哪些是被媒体争夺的话语战场，哪些是值得关注的注意力盲区。

## 输入上下文（USER_TEMPLATE 占位符）

- brief_section       : Brand Brief（主体 + 分析目标）
- research_context_section : 研究问题 + 需求理解
- news_slice_data     : 所有 NewsSlice 的 insight 数据聚合（coverage/narratives/entities/key_quotes）
- market_context      : 知识库 RAG 注入的市场背景（可选）

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

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


SYSTEM_TEMPLATE = """你是资深媒体战略分析师，擅长解读媒体议程（media agenda）与话语结构（discourse）。

## 任务
基于提供的新闻媒体切片数据（NewsSlice insight），输出"媒体议程图"：
媒体当前如何定义、包装、竞争这个品类/议题，主导叙事是什么，存在哪些被争夺的话语战场，
哪些是值得被报道却明显缺位的议题。

## 核心分析框架

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
        {{"quote": "原文引述", "speaker": "发言人", "source": "来源媒体", "source_tier": "tier1/tier2/tier3/wechat_mp"}}
      ],
      "credibility": "high|medium|low",
      "cross_slice_evidence": ["slice_name#1"]
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

## 字段解读

- NewsSlice.result_data.coverage: 报道强度 + 趋势 + 综合指数（media_coverage_index 0-100）
- NewsSlice.result_data.narratives: 已聚合的叙事，直接引用 theme / article_count 作为 heat_rank 依据
- NewsSlice.result_data.key_quotes: 按代表性精选的 quotes，优先作为 representative_voices 来源
- NewsSlice.stats.source_tier_distribution: 各 tier 的文章数量分布
- NewsSlice.stats.sentiment_overall: 该切片的整体情感倾向（-2~2）

## 禁止行为
- 禁止虚构未出现在数据中的引述或来源
- 禁止把"消费者认为"作为论据——该路径只分析媒体视角，消费者声音走 brand_strategy 路径
- 禁止输出与 research_questions 无关的通用媒体观察
"""


USER_TEMPLATE = """{brief_section}

{research_context_section}

{market_context}

## 新闻切片数据

{news_slice_data}"""


def create_agenda_map_chain() -> Runnable:
    """创建 Agenda Map (媒体议程图) LLM 链 — market_report 三层第 1 层"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
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


def _format_news_slices_for_agenda(news_slices: list[dict]) -> str:
    """将 NewsSlice 数据格式化为 Agenda Map 层输入，精选 agenda 分析相关字段。"""
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
            "sentiment_overall": stats.get("sentiment_overall"),
            "coverage": rd.get("coverage"),
            "sentiment": rd.get("sentiment"),
            "narratives": (rd.get("narratives") or [])[:5],
            "entities": [
                {
                    "name": e.get("name"),
                    "role": e.get("role"),
                    "mention_count": e.get("mention_count"),
                    "sentiment": e.get("sentiment"),
                    "source_count": e.get("source_count"),
                    "key_claims": (e.get("key_claims") or [])[:2],
                }
                for e in (rd.get("entities") or [])[:10]
                if isinstance(e, dict)
            ],
            "key_quotes": (rd.get("key_quotes") or [])[:5],
        })

    if not parts:
        return "（新闻切片数据均无有效 insight 结果）"
    return json.dumps(parts, ensure_ascii=False, indent=2)


def format_inputs_for_agenda_map(
    news_slices: list[dict],
    brief: dict | None = None,
    research_design: dict | None = None,
    market_context: str = "",
) -> dict[str, Any]:
    """构建 Agenda Map chain 的输入参数字典。"""
    brief_section = ""
    if brief:
        brief_section = f"## Brand Brief\n{json.dumps(brief, ensure_ascii=False, indent=2)}"

    return {
        "brief_section": brief_section,
        "research_context_section": _build_research_context_section(research_design),
        "market_context": market_context or "",
        "news_slice_data": _format_news_slices_for_agenda(news_slices),
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
