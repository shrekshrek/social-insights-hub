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

## 评估维度
1. **需求覆盖度**：切片数据是否覆盖了 Brief 中明确的分析目标
2. **数据规模**：帖子数量、平台广度是否足够得出有统计意义的结论
3. **竞品覆盖**：Brief 提到的竞品是否有足够的数据
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
  "supplementary_tasks": [
    {{
      "platform": "xiaohongshu",
      "keywords": ["关键词"],
      "reason": "补充原因"
    }}
  ]
}}

## 评分标准
- overall_score: 0-1，综合各维度的加权平均
- is_sufficient: overall_score >= 0.6 时为 true
- coverage_analysis: 5 个维度逐一评分（sufficient/partial/insufficient）
- gap_analysis: 明确指出数据缺口（最多 3 条）
- supplementary_tasks: overall_score < 0.6 时，给出补充采集建议
- 若 overall_score >= 0.6，supplementary_tasks 可为 null
"""

USER_TEMPLATE = """{brief_section}

{slice_plan_section}

{slice_summary_section}"""


def create_strategy_evaluate_chain() -> Runnable:
    """创建 Strategy Evaluate LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_evaluate_inputs(
    brief: dict | None,
    slice_plan: list[dict],
    slices_data: list[dict],
) -> dict[str, Any]:
    """格式化评估链输入"""
    # Brief 段落
    if brief:
        lines = ["## Brand Brief（分析需求）"]
        if brief.get("brand_name"):
            lines.append(f"品牌：{brief['brand_name']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
        if brief.get("competitors"):
            lines.append(f"竞品：{', '.join(brief['competitors'])}")
        if brief.get("focus_areas"):
            lines.append(f"关注维度：{', '.join(brief['focus_areas'])}")
        if brief.get("time_range"):
            lines.append(f"时间范围：{brief['time_range']}")
        brief_section = "\n".join(lines)
    else:
        brief_section = "## Brand Brief（分析需求）\n用户未提供 Brief。"

    # 切片规划段落
    if slice_plan:
        lines = ["## 预期切片规划"]
        for item in slice_plan:
            name = item.get("name", "")
            purpose = item.get("purpose", "")
            lines.append(f"- {name}：{purpose}")
        slice_plan_section = "\n".join(lines)
    else:
        slice_plan_section = "## 预期切片规划\n用户未填写切片规划。"

    # 已关联切片摘要
    if slices_data:
        lines = [f"## 已关联切片数据摘要（共 {len(slices_data)} 个切片）"]
        for i, s in enumerate(slices_data):
            meta = s.get("meta") or {}
            overview = (s.get("foundation") or {}).get("overview") or {}
            lines.append(f"\n### 切片 {i + 1}: {meta.get('subject', '未命名')}")
            if meta.get("competitors"):
                lines.append(f"竞品范围：{meta['competitors']}")
            total_posts = overview.get("total_posts") or overview.get("total_volume")
            if total_posts:
                lines.append(f"帖子总量：{total_posts}")
            platforms = overview.get("unique_platform_volume") or {}
            if platforms:
                lines.append(f"平台分布：{json.dumps(platforms, ensure_ascii=False)}")
        slice_summary_section = "\n".join(lines)
    else:
        slice_summary_section = "## 已关联切片数据摘要\n当前未关联任何切片。"

    return {
        "brief_section": brief_section,
        "slice_plan_section": slice_plan_section,
        "slice_summary_section": slice_summary_section,
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
    result.setdefault("is_sufficient", False)
    result.setdefault("coverage_analysis", [])
    result.setdefault("slice_suggestions", [])
    result.setdefault("gap_analysis", [])
    result.setdefault("supplementary_tasks", None)

    return result
