"""Strategy Architect Chain — 切片结构优化

在充分性评估（Evaluate Chain）之前运行，基于 Brief 目标与全部可用监测项目，
独立判断切片组合结构是否合理，识别未利用的已有数据资源，输出推荐切片结构与
是否仍需补充采集的判断，供 Evaluate Chain 评分时参考。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位社交媒体研究数据架构专家，负责在充分性评估前完成切片结构分析，确保后续评分基于最优数据组织。

## 你的职责

你先于 Evaluate Chain 运行，从**结构与资源**两个视角独立判断：
- 诊断已关联切片中的冗余、重叠、错位问题（结构诊断）
- 对照 Brief 分析目标，发现用户已有但尚未关联的监测切片资源（资源发现）
- 判断通过关联已有切片是否能覆盖 Brief 所有目标，或仍需补充采集新数据
- 给出最优的切片组合方案，Evaluate Chain 将基于此方案评估充分性

## 切片分析模式（与 Evaluate Chain 一致）

1. **品牌聚焦切片**（有 subject）：分析主体明确，含 SWOT/竞品对比，实体分 Target/Competitor/Context
2. **大盘分析切片**（无 subject）：无特定主体，适用于行业趋势/消费场景/市场洞察

## 评估维度

**结构问题诊断**（针对已关联切片）：
- **冗余**：两个切片覆盖高度重叠的品牌+平台+时间范围，数据重复
- **错位**：切片定义（subject/keywords）与其分析目的不符，如用大盘切片做品牌分析
- **缺位**：Brief 明确需要的分析视角（品牌/竞品/大盘）在切片组合中完全缺失
- **过细**：存在多个仅有细微差异的切片，可合并为一个更聚焦的切片

**未利用资源识别**（针对未关联切片）：
- 对照 Brief 分析目标，找出用户已有但尚未关联的切片，其内容能填补 Brief 目标缺口
- 优先推荐「关联已有切片」而非「补充采集新数据」，降低用户成本

## 输出格式

只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "summary": "一句话总结当前切片结构的核心问题或状态",
  "current_slice_issues": [
    {{
      "slice_name": "切片名称",
      "issue_type": "redundant | misaligned | overlapping | too_granular",
      "description": "问题描述",
      "suggestion": "具体改进建议"
    }}
  ],
  "unused_opportunities": [
    {{
      "monitor_name": "监测项目名称",
      "slice_name": "切片名称",
      "gap_addressed": "能填补 Brief 哪个分析目标的缺口",
      "why_valuable": "为什么对这次策略分析有价值",
      "recommended_mode": "品牌聚焦 | 大盘分析",
      "recommended_subject": "若品牌聚焦，建议的分析主体；大盘分析留空字符串"
    }}
  ],
  "recommended_structure": [
    {{
      "name": "推荐切片名称",
      "mode": "品牌聚焦 | 大盘分析",
      "subject": "分析主体（品牌聚焦填写；大盘分析留空字符串）",
      "purpose": "这个切片在策略分析中的角色",
      "action": "keep | associate | adjust | supplement",
      "source": "来源（现有切片名称或监测项目名称）",
      "action_detail": "用户需要执行的具体操作，keep 时可为 null"
    }}
  ],
  "collection_still_needed": false,
  "collection_note": "若 true，说明即使关联所有推荐切片后，仍有哪些 Brief 目标无法被已有数据覆盖，需要补充采集；若 false 可为 null"
}}

## 评分与行动指南

- `action` 字段含义：
  - `keep`：当前已关联，保持不变
  - `associate`：存在于用户已有切片中，直接在策略页面关联即可
  - `adjust`：当前已关联但需调整 scope/subject，用户去分析层修改切片定义
  - `supplement`：需要补充采集新数据后创建，Evaluate Chain 将据此生成具体的采集建议

- `collection_still_needed`：
  - 若所有 Brief 目标都能通过关联已有切片覆盖 → false（Evaluate 无需输出补充采集建议）
  - 若仍有 Brief 目标在已有资源中找不到对应数据 → true（Evaluate 需输出补充采集建议）

- `current_slice_issues` 最多 3 条，聚焦最影响策略质量的问题
- `unused_opportunities` 最多 3 条，按填补缺口的价值排序
- `recommended_structure` 是最终推荐的完整切片组合（2-5 个，以覆盖 Brief 所有分析目标为准，不要凑数），每条有明确行动路径
- 若当前切片结构已经合理，`current_slice_issues` 为空数组，`summary` 说明结构良好

## 数据能力边界（重要）

社媒帖子文本分析的能力边界——评估缺口时必须在此范围内判断：

**能提供**：消费者行为特征（购买动机、使用场景、痛点）、话题讨论内容、情感倾向、品牌认知、竞品对比、KOL传播模式

**无法提供**：年龄/性别/地域等人口统计学画像、兴趣标签（这些是用户账号 profile 数据，不在帖子内容里）

**不要将人口统计学画像缺失列为可通过补充采集解决的问题**，帖子文本无论采集多少都不包含此类结构化用户属性。
"""

USER_TEMPLATE = """{brief_section}

{understanding_section}

{associated_slices_section}

{all_monitors_section}"""


def create_strategy_architect_chain() -> Runnable:
    """创建 Strategy Architect LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def _format_brief_section(brief: dict | None) -> str:
    if not brief:
        return "## Brand Brief\n用户未提供 Brief。"
    lines = ["## Brand Brief"]
    if brief.get("brand_name"):
        lines.append(f"品牌：{brief['brand_name']}")
    if brief.get("analysis_goal"):
        lines.append(f"分析目标：{brief['analysis_goal']}")
    return "\n".join(lines)



def extract_slice_meta(result_data: dict | None) -> dict[str, Any]:
    """从切片 result_data 提取架构分析所需的元信息

    包含：配置信息（subject/competitors/keywords/platforms/date_range）+
    实际数据摘要（entities name+role、topics name+category、帖子量），
    够 LLM 判断切片间冗余/错位/覆盖缺口。
    """
    if not result_data:
        return {}
    meta = result_data.get("meta") or {}
    foundation = result_data.get("foundation") or {}
    overview = foundation.get("overview") or {}
    scope = meta.get("scope") or {}

    subject = meta.get("subject") or None
    competitors = meta.get("competitors") or []
    keywords = scope.get("keywords") or []
    date_from = scope.get("date_from")
    date_to = scope.get("date_to")
    total_posts = overview.get("total_posts") or overview.get("total_volume")
    platforms = list((overview.get("unique_platform_volume") or {}).keys())

    # 实体名单：name + role（判断竞品/主品覆盖）
    raw_entities = foundation.get("aligned_entities") or []
    entities = [
        {"name": e.get("name"), "role": e.get("role")}
        for e in raw_entities[:8]
        if e.get("name")
    ]

    # 话题名单：name + category（判断话题维度覆盖）
    raw_topics = foundation.get("aligned_topics") or []
    topics = [
        {"name": t.get("name"), "category": t.get("category")}
        for t in raw_topics[:8]
        if t.get("name")
    ]

    result: dict[str, Any] = {
        "mode": "品牌聚焦" if subject else "大盘分析",
        "subject": subject,
        "keywords": keywords[:5],
        "total_posts": total_posts,
        "platforms": platforms,
    }
    if competitors:
        result["competitors"] = competitors
    if date_from or date_to:
        result["date_range"] = f"{date_from or '?'} ~ {date_to or '?'}"
    if entities:
        result["entities"] = entities
    if topics:
        result["topics"] = topics
    return result


def _format_slice_entry(s: dict[str, Any], prefix: str = "-") -> list[str]:
    """将单个切片元信息格式化为多行文本（供两个 section 复用）"""
    lines = [f"{prefix} **{s['name']}**  模式：{s['mode']}"]
    row2 = []
    if s.get("subject"):
        row2.append(f"主体：{s['subject']}")
    if s.get("total_posts"):
        row2.append(f"帖子量：{s['total_posts']}")
    if s.get("platforms"):
        row2.append(f"平台：{'、'.join(s['platforms'])}")
    if s.get("date_range"):
        row2.append(f"时间：{s['date_range']}")
    if row2:
        lines.append("  " + "  ".join(row2))
    if s.get("keywords"):
        lines.append(f"  关键词：{', '.join(s['keywords'])}")
    if s.get("competitors"):
        lines.append(f"  竞品配置：{', '.join(s['competitors'])}")
    if s.get("entities"):
        ent_str = "、".join(
            f"{e['name']}({e['role']})" for e in s["entities"]
        )
        lines.append(f"  实体（实际出现）：{ent_str}")
    if s.get("topics"):
        top_str = "、".join(
            f"{t['name']}[{t['category']}]" for t in s["topics"]
        )
        lines.append(f"  话题：{top_str}")
    return lines


def _format_associated_slices_section(
    associated_slices: list[dict[str, Any]],
) -> str:
    """格式化已关联切片摘要"""
    if not associated_slices:
        return "## 已关联切片\n当前策略未关联任何切片。"
    lines = [f"## 已关联切片（共 {len(associated_slices)} 个）"]
    for s in associated_slices:
        lines.extend(_format_slice_entry(s, prefix="-"))
        lines.append("")
    return "\n".join(lines)


def _format_all_monitors_section(
    monitors_data: list[dict[str, Any]],
) -> str:
    """格式化策略关联监测项目及其全部切片（含未关联资源）"""
    if not monitors_data:
        return "## 策略关联监测项目\n暂无监测数据。"
    lines = [f"## 策略关联监测项目（共 {len(monitors_data)} 个，含未关联切片）"]
    for monitor in monitors_data:
        slices = monitor.get("slices") or []
        associated_count = sum(1 for s in slices if s.get("is_associated"))
        lines.append(
            f"\n### {monitor['monitor_name']}"
            f"（{len(slices)} 个切片，已关联 {associated_count} 个）"
        )
        if not slices:
            lines.append("  暂无分析切片")
            continue
        for s in slices:
            tag = "✓ 已关联" if s.get("is_associated") else "○ 未关联"
            entry_lines = _format_slice_entry(s, prefix=f"  [{tag}]")
            lines.extend(entry_lines)
            lines.append("")
    return "\n".join(lines)


def _format_understanding_section(understanding_summary: str | None) -> str:
    """格式化需求理解摘要段落"""
    if not understanding_summary:
        return ""
    return f"## 需求理解摘要（Consult Chain 输出）\n{understanding_summary}"


def format_architect_inputs(
    brief: dict | None,
    associated_slices: list[dict[str, Any]],
    monitors_data: list[dict[str, Any]],
    understanding_summary: str | None = None,
) -> dict[str, str]:
    """格式化 Architect 链输入"""
    return {
        "brief_section": _format_brief_section(brief),
        "understanding_section": _format_understanding_section(understanding_summary),
        "associated_slices_section": _format_associated_slices_section(associated_slices),
        "all_monitors_section": _format_all_monitors_section(monitors_data),
    }


def parse_architect_response(response_text: str) -> dict[str, Any]:
    """解析 Architect Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Architect Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("summary", "")
    result.setdefault("current_slice_issues", [])
    result.setdefault("unused_opportunities", [])
    result.setdefault("recommended_structure", [])
    result.setdefault("collection_still_needed", False)
    result.setdefault("collection_note", None)

    return result
