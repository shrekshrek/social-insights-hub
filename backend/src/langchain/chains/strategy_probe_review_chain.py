"""Strategy Probe Review Chain — 探测数据质量审查

基于探测采集（≈20 条）的分析结果，评估每个关键词×平台任务的话题相关性：
- 客观规则（代码层）：数量、广告占比 → 明确 pass/fail（由调用方处理）
- 语义判断（LLM 层）：话题是否对应研究维度的研究问题（模糊案例）
- 优化建议（LLM 层）：为 fail 任务推荐更合适的关键词（基于实际话题内容）

输出每个任务的 pass/fail 判定、判定依据和（fail 时）关键词建议。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位研究设计顾问，负责评估社交媒体探测采集数据能否支撑研究目标。

## 字段说明

- **主要话题**：从深度分析帖子中聚合出的核心话题，括号内为提及次数，代表该平台用户真实在讨论的内容
- **entity_match**：目标品牌或竞品实体是否在采集内容中出现（true=有出现，false=未出现）
- **广告占比**：被判定为推广/软文的帖子比例

## 判定规则

**核心问题**：话题内容能否支撑该任务所属维度对应的研究问题？

每个任务已标注维度，请只对照该维度下的研究问题进行判断，不要参考其他维度的研究问题。

- **pass**：话题与该维度研究问题的核心关注点有明显关联
- **fail**：话题与该维度研究问题明显无关（收集到的内容完全答不上研究问题）

**保守偏置**：存疑时判 pass——全量采集后分析结果会暴露真正的问题，误判 fail 会浪费关键词调整机会。

## 关键词建议（仅 fail 时填写）

好的替换关键词应满足：在该平台搜索时，能召回与研究问题核心关注点直接相关的内容。
结合「已采集到的话题（知道现在收到了什么）」与「研究问题（知道需要什么）」之间的差距来推导建议词。

## 输出格式（只输出 JSON，不含 markdown）

{{
  "assessments": [
    {{
      "task_id": 123,
      "keyword": "关键词",
      "platform": "平台",
      "verdict": "pass",
      "note": "一句话判定依据（说明话题与研究问题的关联或差距）",
      "suggested_keyword": null,
      "suggestion_reason": null
    }}
  ]
}}

**规则：**
- 每个任务均需给出 assessment
- verdict 只能是 pass 或 fail
- verdict=fail 时：suggested_keyword 给出替换关键词，suggestion_reason 说明「当前收到了什么 vs 需要什么 → 为何推荐这个词」；pass 时均为 null
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
    tasks: list[dict],
) -> dict[str, Any]:
    """格式化探测审查链输入

    Args:
        research_design: 研究计划 JSON
        tasks: 需要 LLM 判定 verdict 的任务（已通过客观规则预筛选，排除明确 pass/fail）
    """
    task_dim_map = research_design.get("_task_dimension_map") or {}

    # 研究背景
    lines = ["## 研究背景"]
    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")

    lines.append("\n### 研究问题（含维度标注）")
    for rq in research_design.get("research_questions", []):
        lines.append(f"- [{rq.get('id')}] {rq.get('question')}（维度：{rq.get('dimension')}）")

    research_design_section = "\n".join(lines)

    # 待判定任务列表
    task_lines = ["## 待判定任务"]
    for t in tasks:
        dim_name = task_dim_map.get(str(t["task_id"]), "")
        task_lines.append(f"\n### 任务 #{t['task_id']}")
        task_lines.append(
            f"关键词: {t.get('keyword', '')} | 平台: {t.get('platform', '')}"
            + (f" | 维度: {dim_name}" if dim_name else "")
        )
        entity_match = t.get("entity_match", False)
        task_lines.append(f"entity_match: {entity_match}（{'品牌/竞品实体在内容中有出现' if entity_match else '��牌/竞品实体未在内容中出现'}）")
        task_lines.append(
            f"采集: {t.get('posts_count', 0)} 条"
            f"（深度分析 {t.get('deep_analyzed', 0)} 条）"
        )

        top_topics = t.get("top_topics") or []
        if top_topics:
            topic_parts = []
            for topic in top_topics[:8]:
                if isinstance(topic, dict):
                    name = topic.get("name", "")
                    mentions = topic.get("mentions")
                    topic_parts.append(f"{name}（{mentions}次）" if mentions else name)
                else:
                    topic_parts.append(str(topic))
            task_lines.append(f"主要话题: {', '.join(topic_parts)}")
        else:
            task_lines.append("主要话题: （暂无，深度分析样本不足）")

        if t.get("promotion_ratio") is not None:
            task_lines.append(f"广告占比: {t['promotion_ratio']:.0%}（推广/软文帖子比例）")

    probe_tasks_section = "\n".join(task_lines)

    return {
        "research_design_section": research_design_section,
        "probe_tasks_section": probe_tasks_section,
    }


def parse_probe_review_response(response_text: str) -> dict[str, Any]:
    """解析探测审查 Chain 输出，失败时抛出 ValueError

    返回 {"assessments": [...]}，每个 assessment 含：
    task_id, keyword, platform, verdict, note, suggested_keyword, suggestion_reason
    """
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Probe Review Chain JSON 解析���败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    result.setdefault("assessments", [])
    return result
