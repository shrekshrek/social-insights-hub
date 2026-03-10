"""Strategy Evaluate Chain — 切片充分性评估

在结构分析（Architect Chain）之后运行，接收 Architect 的推荐资源，
基于"关联推荐切片后的预期状态"评分，仅在必要时输出补充采集建议。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位社交媒体研究数据质量评审专家，在切片结构分析（Architect Chain）之后运行，负责评估数据充分性并给出准确的行动建议。

## 你在流程中的位置

Architect Chain 已先于你完成结构分析：
- 识别了当前切片组合的结构问题
- 发现了用户已有但尚未关联的切片资源（见输入中的「Architect 结构分析结论」）
- 判断了通过关联已有资源能否覆盖所有 Brief 目标

**你的评分基准**：overall_score 反映"用户关联 Architect 推荐切片后的预期充分度"，而非当前状态。你看到的「Architect 结构分析结论」中列出的可关联切片，应视为可立即使用的资源，计入评分。

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

评估时，**已关联切片**和 **Architect 推荐可关联切片**均视为可用资源：

1. **需求覆盖度**：当前切片 + 推荐关联切片组合是否覆盖了 Brief 中的分析目标（品牌视角 + 市场视角）
2. **数据规模**：帖子数量、平台广度是否足够得出有统计意义的结论（推荐切片的规模可从其元信息推断）
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

overall_score 基于"当前切片 + Architect 推荐可关联切片"的预期状态评分：
- 0.85-1.0：充分覆盖所有 Brief 目标，可直接进入策略生成
- 0.75-0.85：基本充分，有小缺口，用户关联推荐切片后可达到就绪状态
- 0.5-0.75：明显不足，即使关联推荐切片后仍有缺口，需要补充采集新数据
- < 0.5：严重不足，建议回「监测规划」重新调整方案

coverage_analysis: 5 个维度逐一评分（sufficient/partial/insufficient），基于预期状态

slice_suggestions: 仅针对**已关联切片的数据质量问题**（如帖子量严重不足、平台覆盖极度单一）
  - **禁止**任何重命名建议：切片名称不影响分析结果，改名无意义
  - **禁止**结构性建议（冗余/重叠/错位）：结构优化已由 Architect Chain 处理
  - **禁止**采集建议：采集相关建议必须放到 supplementary_suggestions
  - 若无数据质量问题，返回空数组 []

gap_analysis: 列出即使关联 Architect 推荐切片后**仍然存在**的数据缺口（最多 3 条）
  - 已能被 Architect 推荐资源覆盖的缺口不要列出

supplementary_suggestions: 有两种触发情况：

  **情况 A（必要补充）**：overall_score < 0.75 且 Architect 判断 collection_still_needed=true
  - 必须输出，不可为 null 或空数组——即使 Architect 没有提供具体的 supplement 切片，也应根据 gap_analysis 自行判断最关键的采集缺口并给出建议

  **情况 B（可选优化）**：overall_score >= 0.75 且 Architect 在 recommended_structure 中有 action=supplement 的切片
  - 应当输出，针对 Architect 推荐补充采集的那些切片给出具体的采集建议
  - 前端会以「可选优化」展示，用户可自行决定是否执行

  **不输出的情况**（此字段为 null）：
  - Architect 判断 collection_still_needed=false → 必须为 null，无论分数高低
  - overall_score < 0.5（严重不足） → 系统自动置空（在 gap_analysis 中建议用户回「监测规划」重新调整）
  - 不属于情况 A 且 Architect 无 supplement 切片 → 为 null

  **通用规则**：
  - **本轮只补最关键的缺口**，用户可多轮评估-补充循环
  - 最多 2 条建议，每条 1-2 个平台、1-2 个关键词，总任务量（建议数 × 平台数）不超过 4
  - 只补 Architect 推荐资源也无法覆盖的维度
  - **关键词选取原则**：
    - 补充的是**品牌相关缺口**时，关键词必须包含 Brief 中的 `brand_name` 或品牌聚焦切片的 `subject`，**禁止仅使用品类词**
    - 补充的是**市场大盘缺口**时，才适合使用品类词或纯场景词
    - 正例：品牌-场景关联不足 → 关键词用「品牌名 + 场景词」（如"大魔王 世界杯"、"大魔王 看球"）
    - 反例：同样缺口下用「品类词 + 场景词」（如"素毛肚 世界杯"）

supplementary_slice_plan: 补充采集完成后如何建切片的简要指引
  - **仅针对 supplementary_suggestions 中的新采集数据**，说明应建什么切片
  - 每条需指定 subject（品牌聚焦）或留空（大盘分析），并说明分析目的
  - **不要**对已有切片的重组/合并提建议——那是结构优化分析的职责
  - 若 supplementary_suggestions 为 null，此字段也为 null

## 数据能力边界（重要）

社媒帖子文本分析的能力边界——评估缺口和给出补充建议时必须在此范围内：

**能提供**：消费者行为特征（购买动机、使用场景、痛点）、话题讨论内容、情感倾向、品牌认知、竞品对比

**无法提供**：年龄/性别/地域等人口统计学画像、兴趣标签（这些是用户账号 profile 数据，不在帖子内容里）

**不要将人口统计学画像缺失列入 gap_analysis，也不要在 supplementary_suggestions 中建议采集此类数据**。
"""

USER_TEMPLATE = """{brief_section}

{understanding_section}

{architect_recommendations_section}

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


def _format_architect_recommendations_section(
    unused_opportunities: list[dict],
    collection_still_needed: bool,
    supplement_items: list[dict] | None = None,
) -> str:
    """格式化 Architect Chain 的结构分析结论，供 Evaluate 评分时参考"""
    lines = ["## Architect 结构分析结论"]
    if unused_opportunities:
        lines.append(
            "以下切片已存在于用户监测数据中但尚未关联本策略，"
            "评分时应将其纳入考量（视为可立即使用的资源）："
        )
        for op in unused_opportunities:
            monitor = op.get("monitor_name", "")
            name = op.get("slice_name", "")
            gap = op.get("gap_addressed", "")
            why = op.get("why_valuable", "")
            lines.append(f"- 【{monitor} / {name}】填补：{gap}；价值：{why}")
    else:
        lines.append("当前已关联切片在结构上已较完整，无额外可关联资源。")

    if supplement_items:
        lines.append(
            "\nArchitect 推荐补充采集后新建的切片"
            "（这些切片在已有数据中不存在，需要采集新数据才能创建）："
        )
        for item in supplement_items:
            name = item.get("name", "")
            mode = item.get("mode", "")
            subject = item.get("subject", "")
            purpose = item.get("purpose", "")
            mode_str = f"{mode}（主体：{subject}）" if subject else mode
            lines.append(f"- 【{name}】{mode_str}：{purpose}")
        lines.append(
            "\n你的 supplementary_suggestions 和 supplementary_slice_plan 必须能支撑上述切片的创建。"
            "关键词和平台选取需精准匹配每个切片所需的分析视角（品牌聚焦切片关键词必须包含品牌名）。"
        )

    if collection_still_needed:
        lines.append(
            "\nArchitect 判断：即使关联上述推荐切片，仍有 Brief 目标无法被已有数据覆盖，"
            "需要补充采集。请在 supplementary_suggestions 中给出采集建议。"
        )
    else:
        lines.append(
            "\nArchitect 判断：已有资源（含推荐关联切片）可覆盖所有 Brief 目标，"
            "supplementary_suggestions 应为 null，无需采集新数据。"
        )
    return "\n".join(lines)


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
    architect_unused_opportunities: list[dict] | None = None,
    architect_collection_still_needed: bool = True,
    architect_supplement_items: list[dict] | None = None,
) -> dict[str, Any]:
    """格式化评估链输入

    传入切片的「名单级摘要」：实体/话题/品牌/痛点的名字列表 + 数据规模。
    够 LLM 判断覆盖度（Brief 要的竞品/维度/平台有没有），
    不传 heat/sentiment 等分析细节（那是策略生成链的事）。
    architect_unused_opportunities: Architect Chain 识别的可关联已有切片，
        Evaluate 据此判断哪些缺口可通过关联解决（无需补充采集）。
    architect_supplement_items: Architect 推荐通过补充采集新建的切片，
        Evaluate 的 supplementary_suggestions/slice_plan 应与之对齐。
    """
    brief_section = _format_brief_section(brief)
    understanding_section = _format_understanding_section(understanding_summary)
    architect_recommendations_section = _format_architect_recommendations_section(
        unused_opportunities=architect_unused_opportunities or [],
        collection_still_needed=architect_collection_still_needed,
        supplement_items=architect_supplement_items or [],
    )
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
        "architect_recommendations_section": architect_recommendations_section,
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
