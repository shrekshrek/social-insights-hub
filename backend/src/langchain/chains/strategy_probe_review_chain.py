"""Strategy Probe Review Chain — 探测数据质量审查

基于探测采集（≈15 条）的分析结果，评估每个任务的关键词质量：
- 实体命中率（采集数据是否包含目标品牌/竞品）
- 话题相关性（内容是否围绕目标话题）
- 数据质量（是否有足够有意义的内容）

输出每个任务的 pass/fail 判定和优化建议。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据质量审查专家，负责评估社交媒体探测采集数据是否满足研究需求。

## 任务
根据探测采集（每个搜索任务约 15 条帖子）的分析摘要，判断关键词质量并给出优化建议。

## 评估维度
1. **相关性** (relevance): 采集到的内容是否与研究目标相关
2. **实体命中** (entity_match): 分析结果中是否出现目标品牌/竞品实体
3. **数据质量** (quality): 内容是否有意义（非纯广告/spam/无关内容）

## 判定标准
- **pass**: 相关性高、实体命中符合预期、数据质量可接受
- **adjust**: 数据有一定价值但关键词需要微调（如太宽泛或太狭窄）
- **fail**: 数据几乎不相关，关键词需要大幅调整

## 输出格式
只输出 JSON，不要额外文字或 markdown 代码块标记：
{{
  "assessments": [
    {{
      "task_id": 123,
      "keyword": "原始搜索关键词",
      "platform": "平台名称",
      "relevance_rate": 0.8,
      "entity_match": true,
      "topic_relevance": "high",
      "quality": "good",
      "verdict": "pass",
      "note": "一句话评价"
    }}
  ],
  "overall_verdict": "all_pass",
  "refinement_suggestions": [
    {{
      "task_id": 456,
      "original_keyword": "原关键词",
      "suggested_keyword": "建议新关键词",
      "platform": "平台名称",
      "reason": "调整原因"
    }}
  ]
}}

relevance_rate: 0.0-1.0 之间的相关性评分
topic_relevance: high / medium / low
quality: good / acceptable / poor
verdict: pass / adjust / fail
overall_verdict:
- all_pass: 所有任务都通过
- partial_pass: 部分通过，部分需要调整
- fail: 大部分不通过

## 要求
- assessments 必须覆盖每个探测任务
- 只有 verdict 为 adjust 或 fail 的任务才需要 refinement_suggestions
- 如果全部 pass，refinement_suggestions 为空数组
- 判定要务实，探测数据量小（≈15条），不要因为数据量少就判 fail
"""

USER_TEMPLATE = """{research_design_section}

{probe_tasks_section}"""


def create_probe_review_chain() -> Runnable:
    """创建探测审查 LLM 链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_probe_review_inputs(
    research_design: dict,
    probe_tasks: list[dict],
) -> dict[str, Any]:
    """格式化探测审查链输入

    Args:
        research_design: 研究计划 JSON
        probe_tasks: 每个任务的探测分析摘要列表，每个包含:
            task_id, keyword, platform, posts_count,
            top_entities, top_topics, sentiment_summary
    """
    # 研究计划摘要
    lines = ["## 研究计划"]
    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")

    for rq in research_design.get("research_questions", []):
        lines.append(f"- [{rq.get('id')}] {rq.get('question')} (维度: {rq.get('dimension')})")

    lines.append("\n## 数据采集方案")
    for dp in research_design.get("data_plan", []):
        keywords = ", ".join(dp.get("keywords", []))
        platforms = ", ".join(dp.get("platforms", []))
        lines.append(f"- {dp.get('dimension_name')}: 关键词=[{keywords}], 平台=[{platforms}]")

    research_design_section = "\n".join(lines)

    # 探测任务摘要
    task_lines = ["## 探测采集结果"]
    for task_info in probe_tasks:
        task_lines.append(f"\n### 任务 #{task_info['task_id']}")
        task_lines.append(f"关键词: {task_info.get('keyword', '')}")
        task_lines.append(f"平台: {task_info.get('platform', '')}")
        task_lines.append(f"采集帖子数: {task_info.get('posts_count', 0)}")

        if task_info.get("top_entities"):
            entities_str = ", ".join(task_info["top_entities"][:10])
            task_lines.append(f"主要实体: {entities_str}")

        if task_info.get("top_topics"):
            topics_str = ", ".join(task_info["top_topics"][:10])
            task_lines.append(f"主要话题: {topics_str}")

        if task_info.get("sentiment_summary"):
            task_lines.append(f"情感摘要: {task_info['sentiment_summary']}")

        if task_info.get("analysis_summary"):
            task_lines.append(f"分析摘要: {task_info['analysis_summary']}")

    probe_tasks_section = "\n".join(task_lines)

    return {
        "research_design_section": research_design_section,
        "probe_tasks_section": probe_tasks_section,
    }


def parse_probe_review_response(response_text: str) -> dict[str, Any]:
    """解析探测审查 Chain 输出，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Probe Review Chain JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("assessments", [])
    result.setdefault("overall_verdict", "fail")
    result.setdefault("refinement_suggestions", [])

    return result
