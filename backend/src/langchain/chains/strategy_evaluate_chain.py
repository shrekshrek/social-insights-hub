"""Strategy Evaluate Chain — 切片充分性评估

评估已关联切片是否满足 Brand Brief 的分析需求，输出充分性评分与缺口分析。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位社交媒体研究数据质量评审专家，负责评估已采集数据是否足够支撑策略分析需求。

## 切片分析模式

切片是数据分析的基本单元，有两种模式：

1. **品牌聚焦切片**（有 subject）：
   - subject 是分析主体（品牌/产品名），如 "大魔王"、"元气森林"
   - 包含 Focus 层（SWOT、竞品对比、产品健康度）
   - 实体按角色分类：Target（本品）、Competitor（竞品）、Context（其他）
   - 适用于：品牌诊断、竞品分析、产品口碑分析

2. **大盘分析切片**（无 subject）：
   - 没有特定分析主体，不生成 Focus 层
   - 所有实体均为 Context 角色
   - 适用于：行业趋势、市场大盘、场景研判、消费者需求洞察

**重要**：评估时要理解每个切片的定位，不要把大盘切片误判为"主题不明确"，也不要要求品牌聚焦切片覆盖大盘趋势。应当从整体组合的角度判断切片集是否满足 Brief 需求。

## 评估维度
1. **需求覆盖度**：切片组合是否覆盖了 Brief 中的分析目标（品牌视角 + 市场视角）
2. **数据规模**：帖子数量、平台广度是否足够得出有统计意义的结论
3. **竞品覆盖**：Brief 提到的竞品是否在品牌聚焦切片的实体中出现
4. **时间跨度**：数据时间范围是否符合分析需求
5. **话题深度**：关键话题是否有足够的讨论深度

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "overall_score": 0.75,
  "is_sufficient": true,
  "coverage_analysis": [
    {{
      "dimension": "需求覆盖度",
      "score": 0.8,
      "status": "sufficient",
      "note": "核心分析目标已覆盖"
    }}
  ],
  "slice_suggestions": [
    {{
      "slice_name": "切片名称",
      "issue": "问题描述",
      "suggestion": "改进建议"
    }}
  ],
  "gap_analysis": [
    {{
      "gap_type": "missing_competitor",
      "description": "缺少竞品X的数据",
      "priority": "high"
    }}
  ],
  "supplementary_suggestions": [
    {{
      "name": "补充采集名称",
      "platforms": ["xiaohongshu"],
      "keywords": ["关键词1", "关键词2"],
      "rationale": "补充原因"
    }}
  ],
  "supplementary_slice_plan": [
    {{
      "name": "建议切片名称",
      "subject": "分析主体品牌/产品名（品牌聚焦填写；大盘分析留空字符串）",
      "purpose": "分析目的",
      "expected_sources": ["补充采集名称", "已有切片名称"]
    }}
  ]
}}

## 评分标准
- overall_score: 0-1，综合各维度的加权平均，参照以下锚点校准：
  - 0.85-1.0：各维度充分覆盖，可直接进入策略生成
  - 0.75-0.85：基本充分，有小缺口，建议微调
  - 0.5-0.75：明显不足，需要补充采集
  - < 0.5：严重不足，建议回「监测规划」重新调整方案
- coverage_analysis: 5 个维度逐一评分（sufficient/partial/insufficient）
- slice_suggestions: 仅针对**已有切片的元信息**优化（重命名、调整分析目的等）
  - 理解每个切片的 mode（品牌聚焦 vs 大盘分析），在正确定位下给出改进建议
  - 不要建议大盘切片"明确主体"（那就不是大盘分析了），也不要建议品牌切片"扩大视野"
  - **禁止**在此字段放采集建议（如"补充关键词"、"增加平台"），采集相关建议必须放到 supplementary_suggestions
  - **禁止**在此字段指出结构性问题（冗余/重叠/错位），结构优化由专项分析处理
- gap_analysis: 从切片组合整体角度指出数据缺口（最多 3 条）
- supplementary_suggestions: 当存在数据缺口时给出补充采集建议
  - **本轮只补最关键的缺口**，用户可多轮评估-补充循环，不必一次补齐所有缺失
  - 最多 2 条建议，每条 1-2 个平台、1-2 个关键词，总任务量（建议数 × 平台数）不超过 4
  - 只补缺失维度，不重复已有数据
  - 若 overall_score < 0.5（严重不足），在 gap_analysis 中建议用户回「监测规划」阶段重新调整初始采集方案（supplementary_suggestions 由系统自动置空，无需输出）
  - 若所有维度均充分覆盖，可为 null
  - **关键词选取原则**：
    - 补充的是**品牌相关缺口**（品牌声量不足、品牌-场景关联缺失、品牌竞品对比不足）时，关键词必须包含 Brief 中的 `brand_name` 或品牌聚焦切片的 `subject`，**禁止仅使用品类词**（品类词无品牌锚点，采集结果会混入大量竞品和无关内容，无法支撑品牌分析）
    - 补充的是**市场大盘缺口**（行业趋势、消费场景、用户需求洞察）时，才适合使用品类词或纯场景词
    - 正例：品牌-场景关联不足 → 关键词用「品牌名 + 场景词」（如"大魔王 世界杯"、"大魔王 看球"）
    - 反例：同样缺口下用「品类词 + 场景词」（如"素毛肚 世界杯"）— 这无法保证采集到品牌相关数据
- supplementary_slice_plan: 补充采集完成后如何建切片的简要指引
  - **仅针对 supplementary_suggestions 中的新采集数据**，说明采集完成后应建什么切片
  - 每条需指定 subject（品牌聚焦）或留空（大盘分析），并说明分析目的
  - **不要**对已有切片的重组/合并/调整提建议——那是结构优化分析的职责
  - 若 supplementary_suggestions 为 null，此字段也为 null
"""

USER_TEMPLATE = """{brief_section}

{understanding_section}

{slice_plan_section}

{slice_data_section}"""


def create_strategy_evaluate_chain() -> Runnable:
    """创建 Strategy Evaluate LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def _format_brief_section(brief: dict | None) -> str:
    """格式化 Brief 段落"""
    if not brief:
        return "## Brand Brief（分析需求）\n用户未提供 Brief。"
    lines = ["## Brand Brief（分析需求）"]
    if brief.get("brand_name"):
        lines.append(f"品牌：{brief['brand_name']}")
    if brief.get("analysis_goal"):
        lines.append(f"分析目标：{brief['analysis_goal']}")
    return "\n".join(lines)


def _format_understanding_section(understanding_summary: str | None) -> str:
    """格式化需求理解摘要段落"""
    if not understanding_summary:
        return ""
    return f"## 需求理解摘要（Consult Chain 输出）\n{understanding_summary}"


def _format_slice_plan_section(slice_plan: list[dict]) -> str:
    """格式化切片规划段落"""
    if not slice_plan:
        return "## 初始切片规划（仅供参考）\n用户未填写切片规划。"
    lines = [
        "## 初始切片规划（仅供参考）",
        "注意：此为监测规划阶段的初始设计，用户实际创建的切片可能有所调整，以「已关联切片数据」为准，不因偏离此规划而扣分。",
    ]
    for item in slice_plan:
        name = item.get("name", "")
        purpose = item.get("purpose", "")
        lines.append(f"- {name}：{purpose}")
    return "\n".join(lines)


def _extract_slice_part(s: dict, index: int, slice_name: str | None = None) -> dict[str, Any]:
    """从单个切片 result_data 提取评估所需的「名单级摘要」

    目标是让 LLM 判断覆盖度，不需要分析数据含义。
    只传名字/角色/数量，不传 heat/sentiment 等分析细节。

    切片有两种模式：
    - 有 subject：品牌聚焦分析，含 Focus 层（SWOT/竞品对比），实体分 Target/Competitor/Context
    - 无 subject：大盘分析，无 Focus 层，所有实体为 Context 角色
    """
    meta = s.get("meta") or {}
    foundation = s.get("foundation") or {}
    overview = foundation.get("overview") or {}
    layers = s.get("layers") or {}

    # 切片身份信息
    subject = meta.get("subject") or None
    competitors = meta.get("competitors") or []
    scope = meta.get("scope") or {}

    # 实体名单（仅 name + role，判断品牌/竞品覆盖）
    entities = foundation.get("aligned_entities", [])[:10]
    entity_names = [
        {"name": e.get("name"), "role": e.get("role")}
        for e in entities
    ]

    # 话题名单（仅 name + category，判断维度覆盖）
    topics = foundation.get("aligned_topics", [])[:15]
    topic_names = [
        {"name": t.get("name"), "category": t.get("category")}
        for t in topics
    ]

    # SOV 品牌名单（仅 name，判断竞品覆盖）
    landscape = layers.get("landscape") or {}
    sov_names = [
        r.get("name") for r in (landscape.get("sov_ranking") or [])[:10]
    ]

    # topic_radar 名单（仅 name，判断话题深度）
    intent = layers.get("intent") or {}
    topic_radar = intent.get("topic_radar") or {}
    pain_names = [
        p.get("name") for p in (topic_radar.get("pains") or [])[:10]
        if isinstance(p, dict)
    ]
    gain_names = [
        g.get("name") for g in (topic_radar.get("gains") or [])[:5]
        if isinstance(g, dict)
    ]
    controversy_names = [
        c.get("name") for c in (topic_radar.get("controversies") or [])[:5]
        if isinstance(c, dict)
    ]

    # 数据规模
    total_posts = overview.get("total_posts") or overview.get("total_volume")
    platforms = overview.get("unique_platform_volume") or {}

    # Focus 层存在性（仅品牌聚焦切片有）
    focus = (layers.get("focus") or {})
    has_focus = bool(focus.get("swot") or focus.get("gap"))

    part: dict[str, Any] = {
        "slice_index": index,
        "name": slice_name or f"切片 {index}",
        "mode": "品牌聚焦" if subject else "大盘分析",
        "subject": subject,
        "competitors": competitors if competitors else None,
        "keywords": scope.get("keywords"),
        "has_focus_layer": has_focus,
        "total_posts": total_posts,
        "platforms": platforms if platforms else None,
        "entity_count": len(entities),
        "entities": entity_names,
        "topic_count": len(topics),
        "topics": topic_names,
        "sov_brands": sov_names if sov_names else None,
    }
    # 条件添加非空名单
    if pain_names:
        part["pains"] = pain_names
    if gain_names:
        part["gains"] = gain_names
    if controversy_names:
        part["controversies"] = controversy_names
    return part


def format_evaluate_inputs(
    brief: dict | None,
    slice_plan: list[dict],
    slices_data: list[dict],
    slice_names: list[str | None] | None = None,
    understanding_summary: str | None = None,
) -> dict[str, Any]:
    """格式化评估链输入

    传入切片的「名单级摘要」：实体/话题/品牌/痛点的名字列表 + 数据规模。
    够 LLM 判断覆盖度（Brief 要的竞品/维度/平台有没有），
    不传 heat/sentiment 等分析细节（那是策略生成链的事）。
    """
    brief_section = _format_brief_section(brief)
    understanding_section = _format_understanding_section(understanding_summary)
    slice_plan_section = _format_slice_plan_section(slice_plan)

    names = slice_names or [None] * len(slices_data)

    if slices_data:
        slice_parts = [
            _extract_slice_part(s, i, slice_name=names[i] if i < len(names) else None)
            for i, s in enumerate(slices_data)
        ]
        slice_data_section = (
            f"## 已关联切片数据（共 {len(slices_data)} 个切片）\n"
            + json.dumps(slice_parts, ensure_ascii=False, indent=2)
        )
    else:
        slice_data_section = "## 已关联切片数据\n当前未关联任何切片。"

    return {
        "brief_section": brief_section,
        "understanding_section": understanding_section,
        "slice_plan_section": slice_plan_section,
        "slice_data_section": slice_data_section,
    }


def parse_evaluate_response(response_text: str) -> dict[str, Any]:
    """解析评估 Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Evaluate Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    # 确保必要字段存在
    result.setdefault("overall_score", 0.0)
    result.setdefault("coverage_analysis", [])
    result.setdefault("slice_suggestions", [])
    result.setdefault("gap_analysis", [])
    result.setdefault("supplementary_suggestions", None)
    result.setdefault("supplementary_slice_plan", None)

    # 确定性规则：由代码保证，不依赖 LLM 输出
    score: float = result["overall_score"]
    result["is_sufficient"] = score >= 0.75
    if score < 0.5:
        result["supplementary_suggestions"] = None
        result["supplementary_slice_plan"] = None

    return result
