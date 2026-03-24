"""Strategy Coverage Check Chain — 数据覆盖度验证

基于切片 result_data 摘要，对照研究问题评估数据覆盖度。
替代原有 architect_chain + evaluate_chain 组合。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据覆盖度评估专家，负责判断已有数据是否足以回答研究问题。

## 任务
根据研究问题列表和切片分析摘要，评估数据覆盖度并给出就绪判定。

## 评估逻辑
1. 逐个研究问题检查：该问题需要的数据是否在某个切片中有所体现
2. 覆盖判定依据：切片中出现相关实体、话题、情感数据即视为覆盖
3. 整体判定：所有 high-priority 问题被覆盖 → overall_ready = true

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "question_coverage": [
    {{
      "question_id": "rq1",
      "question": "研究问题内容",
      "covered": true,
      "covered_by": ["切片名称1"],
      "note": "覆盖说明"
    }}
  ],
  "overall_ready": true,
  "data_highlights": ["数据亮点1", "数据亮点2"],
  "slice_adjustments": [
    {{
      "slice_name": "切片名称",
      "issue": "问题描述",
      "suggestion": "调整建议"
    }}
  ]
}}

## 要求
- question_coverage 必须覆盖所有研究问题
- overall_ready = true 的条件：所有 high priority 问题都被覆盖
- data_highlights: 2-4 条数据亮点（有助于生成策略的关键发现）
- slice_adjustments: 只在有切片配置问题时才输出，否则空数组
- 判定要务实，不要过于严格（数据有相关性即可，不要求完美覆盖）
"""

USER_TEMPLATE = """{brief_section}

{research_questions_section}

{slices_summary_section}"""


def create_coverage_check_chain() -> Runnable:
    """创建覆盖度验证 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_coverage_check_inputs(
    brief: dict | None,
    research_questions: list[dict],
    slices_data: list[tuple[str, dict]],
) -> dict[str, Any]:
    """格式化覆盖度验证链输入

    Args:
        brief: Brand Brief dict
        research_questions: 研究问题列表
        slices_data: [(slice_name, result_data), ...] 切片名和分析结果
    """
    # Brief
    if brief:
        lines = ["## Brand Brief"]
        if brief.get("brand_name"):
            lines.append(f"品牌：{brief['brand_name']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
        brief_section = "\n".join(lines)
    else:
        brief_section = "## Brand Brief\n未提供"

    # 研究问题
    rq_lines = ["## 研究问题"]
    for rq in research_questions:
        priority = rq.get("priority", "medium")
        rq_lines.append(
            f"- [{rq.get('id')}] {rq.get('question')} "
            f"(维度: {rq.get('dimension')}, 优先级: {priority})"
        )
    research_questions_section = "\n".join(rq_lines)

    # 切片摘要
    slice_lines = ["## 切片分析摘要"]
    for name, data in slices_data:
        slice_lines.append(f"\n### {name}")
        overview = data.get("overview", {})
        slice_lines.append(f"帖子数: {overview.get('total_posts', 0)}")

        # 实体
        entities = data.get("aligned_entities", [])[:10]
        if entities:
            entity_names = [f"{e.get('name', '')}({e.get('role', '')})" for e in entities]
            slice_lines.append(f"主要实体: {', '.join(entity_names)}")

        # 话题
        topics = data.get("aligned_topics", [])[:10]
        if topics:
            topic_names = [t.get("name", "") for t in topics]
            slice_lines.append(f"主要话题: {', '.join(topic_names)}")

        # 情感
        sentiment = overview.get("sentiment_label", "")
        if sentiment:
            slice_lines.append(f"整体情感: {sentiment}")

        # SOV
        sov = data.get("sov_ranking", [])[:5]
        if sov:
            sov_names = [s.get("name", "") for s in sov]
            slice_lines.append(f"声量排名: {', '.join(sov_names)}")

    slices_summary_section = "\n".join(slice_lines)

    return {
        "brief_section": brief_section,
        "research_questions_section": research_questions_section,
        "slices_summary_section": slices_summary_section,
    }


def parse_coverage_check_response(response_text: str) -> dict[str, Any]:
    """解析覆盖度验证 Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Coverage Check Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("question_coverage", [])
    result.setdefault("overall_ready", False)
    result.setdefault("data_highlights", [])
    result.setdefault("slice_adjustments", [])

    return result
