"""Strategy Architect Chain — 切片结构优化

在充分性评估（Evaluate Chain）之后运行，基于全部可用监测项目分析切片组合是否
合理，识别未利用的数据资源，输出推荐的最优切片结构方案。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位社交媒体研究数据架构专家，负责优化分析切片的组合结构，确保进入策略生成前数据组织最合理。

## 你的职责

Evaluate Chain 已完成充分性评估（数据够不够），你专注于**结构质量**（数据组织得好不好）：
- 诊断已关联切片中的冗余、重叠、错位问题
- 发现用户已有但尚未关联的监测切片资源
- 给出最优的切片组合方案，指导用户在确认就绪前完成结构调整

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
- 用户已有但尚未关联的切片，其内容能填补 Evaluate 识别的缺口
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
      "gap_addressed": "能填补 Evaluate 指出的哪个缺口",
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
  "collection_note": "若 true，说明结构优化后仍有哪些数据缺口无法通过已有资源覆盖，需配合 Evaluate 的补充采集建议；若 false 可为 null"
}}

## 评分与行动指南

- `action` 字段含义：
  - `keep`：当前已关联，保持不变
  - `associate`：存在于用户已有切片中，直接在策略页面关联即可
  - `adjust`：当前已关联但需调整 scope/subject，用户去分析层修改切片定义
  - `supplement`：需要补充采集新数据后创建，配合 Evaluate 的补充建议

- `collection_still_needed`：
  - 若所有缺口都能通过关联已有切片解决 → false（Evaluate 的补充采集建议可暂缓）
  - 若仍有缺口在已有资源中找不到 → true（仍需执行 Evaluate 的补充建议）

- `current_slice_issues` 最多 3 条，聚焦最影响策略质量的问题
- `unused_opportunities` 最多 3 条，按填补缺口的价值排序
- `recommended_structure` 是最终推荐的完整切片组合（2-5 个，以覆盖 Brief 所有分析目标为准，不要凑数），每条有明确行动路径
- 若当前切片结构已经合理，`current_slice_issues` 为空数组，`summary` 说明结构良好
"""

USER_TEMPLATE = """{brief_section}

{understanding_section}

{evaluate_gaps_section}

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


def _format_evaluate_gaps_section(gap_analysis: list[dict]) -> str:
    """格式化 Evaluate Chain 输出的缺口分析"""
    if not gap_analysis:
        return "## 充分性评估缺口\n本次评估未识别到明显缺口。"
    lines = ["## 充分性评估缺口（Evaluate Chain 输出）"]
    for gap in gap_analysis:
        priority = gap.get("priority", "")
        desc = gap.get("description", "")
        gap_type = gap.get("gap_type", "")
        line = f"- [{priority.upper()}] {desc}"
        if gap_type:
            line += f"（类型：{gap_type}）"
        lines.append(line)
    return "\n".join(lines)


def extract_slice_meta(result_data: dict | None) -> dict[str, Any]:
    """从切片 result_data 提取架构分析所需的轻量元信息"""
    if not result_data:
        return {}
    meta = result_data.get("meta") or {}
    foundation = result_data.get("foundation") or {}
    overview = foundation.get("overview") or {}
    subject = meta.get("subject") or None
    keywords = (meta.get("scope") or {}).get("keywords") or []
    total_posts = overview.get("total_posts") or overview.get("total_volume")
    platforms = list((overview.get("unique_platform_volume") or {}).keys())
    return {
        "mode": "品牌聚焦" if subject else "大盘分析",
        "subject": subject,
        "keywords": keywords[:5],
        "total_posts": total_posts,
        "platforms": platforms,
    }


def _format_associated_slices_section(
    associated_slices: list[dict[str, Any]],
) -> str:
    """格式化已关联切片摘要"""
    if not associated_slices:
        return "## 已关联切片\n当前策略未关联任何切片。"
    lines = [f"## 已关联切片（共 {len(associated_slices)} 个）"]
    for s in associated_slices:
        parts = [f"- **{s['name']}**", f"模式：{s['mode']}"]
        if s.get("subject"):
            parts.append(f"主体：{s['subject']}")
        if s.get("keywords"):
            parts.append(f"关键词：{', '.join(s['keywords'])}")
        if s.get("total_posts"):
            parts.append(f"帖子量：{s['total_posts']}")
        if s.get("platforms"):
            parts.append(f"平台：{', '.join(s['platforms'])}")
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _format_all_monitors_section(
    monitors_data: list[dict[str, Any]],
) -> str:
    """格式化所有可用监测项目及其切片"""
    if not monitors_data:
        return "## 所有可用监测项目\n用户暂无其他监测数据。"
    lines = [f"## 所有可用监测项目（共 {len(monitors_data)} 个，含未关联资源）"]
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
            parts = [f"  [{tag}] **{s['name']}**", f"模式：{s['mode']}"]
            if s.get("subject"):
                parts.append(f"主体：{s['subject']}")
            if s.get("keywords"):
                parts.append(f"关键词：{', '.join(s['keywords'])}")
            if s.get("total_posts"):
                parts.append(f"帖子量：{s['total_posts']}")
            if s.get("platforms"):
                parts.append(f"平台：{', '.join(s['platforms'])}")
            lines.append("  ".join(parts))
    return "\n".join(lines)


def _format_understanding_section(understanding_summary: str | None) -> str:
    """格式化需求理解摘要段落"""
    if not understanding_summary:
        return ""
    return f"## 需求理解摘要（Consult Chain 输出）\n{understanding_summary}"


def format_architect_inputs(
    brief: dict | None,
    gap_analysis: list[dict],
    associated_slices: list[dict[str, Any]],
    monitors_data: list[dict[str, Any]],
    understanding_summary: str | None = None,
) -> dict[str, str]:
    """格式化 Architect 链输入"""
    return {
        "brief_section": _format_brief_section(brief),
        "understanding_section": _format_understanding_section(understanding_summary),
        "evaluate_gaps_section": _format_evaluate_gaps_section(gap_analysis),
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
