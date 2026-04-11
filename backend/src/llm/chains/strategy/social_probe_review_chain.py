"""Strategy Social Probe Review Chain — 社媒探测数据质量审查

与 `news_probe_review_chain` 对称，专门审查策略研究流程中 social_media 渠道的 probe 任务。
基于探测采集（≈20 条）的分析结果，评估每个关键词×平台任务的话题相关性：
- 客观规则（代码层）：数量、广告占比 → 明确 pass/fail（由调用方处理）
- 语义判断（LLM 层）：话题是否对应研究维度的研究问题（模糊案例）
- 优化建议（LLM 层）：为 fail 任务推荐更合适的关键词

每个任务独立并行评估（SINGLE_TASK_SYSTEM_TEMPLATE），消除批量上下文的锚定效应。
输出每个任务的 pass/fail 判定、判定依据、关键词建议。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SINGLE_TASK_SYSTEM_TEMPLATE = """你是一位研究设计顾问，负责评估单个社交媒体采集任务的话题相关性。

## 字段说明

- **主要话题**：从深度分析帖子中聚合出的核心话题，括号内为提及次数，代表该平台用户真实在讨论的内容
- **entity_match**：目标品牌或竞品实体是否在采集内容中出现（true=有出现，false=未出现）
- **广告占比**：被判定为推广/软文的帖子比例

## 判定规则

**核心问题**：话题内容能否支撑该任务所属维度对应的研究问题？

每个任务已标注维度，请只对照该维度下的研究问题进行判断。

- **pass**：话题与该维度研究问题的核心关注点有明显关联
- **fail**：话题与该维度研究问题明显无关（收集到的内容完全答不上研究问题）

**保守偏置**：存疑时判 pass——全量采集后分析结果会暴露真正的问题，误判 fail 会浪费关键词调整机会。

## 关键词建议（仅 fail 时填写）

好的替换关键词应满足：在该平台搜索时，能召回与研究问题核心关注点直接相关的内容。
结合「已采集到的话题（知道现在收到了什么）」与「研究问题（知道需要什么）」之间的差距来推导建议词。
**suggested_keyword 是提交给平台的单一搜索查询**（可包含空格），禁止用 `|` 拼接多个备选查询。
如果 fail 的原因是「该平台本身不适合此类研究」，可将 suggested_keyword 设为 null，表示建议直接移除。

各平台替换词格式参考：
- 知乎：加"怎么样/如何评价"等评价词能精准命中问题标题，纯品牌名召回较泛
- 微博：品牌名 + 口碑类词（口碑/评价/怎么样）效果好；纯品牌名噪音大
- 小红书：加"测评/体验/推荐/避坑"类词能精准召回消费者评价
- 抖音/B站：简短品牌名 + 场景词/评测词效果好

## 输出格式（只输出 JSON，不含 markdown）

{{
  "task_id": 123,
  "keyword": "关键词",
  "platform": "平台",
  "verdict": "pass",
  "note": "一句话判定依据（说明话题与研究问题的关联或差距）",
  "suggested_keyword": null,
  "suggestion_reason": null
}}

**规则：**
- verdict 只能是 pass 或 fail
- verdict=fail 时：suggested_keyword 给出替换关键词，suggestion_reason 说明「当前收到了什么 vs 需要什么 → 为何推荐这个词」；pass 时均为 null
"""

USER_TEMPLATE = """{research_design_section}

{probe_tasks_section}"""


def create_single_task_probe_review_chain() -> Runnable:
    """创建单任务探测审查 LLM 链（用于并行评估，每个任务独立调用）"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SINGLE_TASK_SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_single_task_probe_review_inputs(
    research_design: dict,
    task: dict,
    brief: dict | None = None,
) -> dict[str, Any]:
    """格式化单任务探测审查输入（供并行调用使用）"""
    task_dim_map = research_design.get("_task_dimension_map") or {}
    data_plan = research_design.get("data_plan", [])
    all_rqs = research_design.get("research_questions", [])

    rq_by_id = {rq.get("id"): rq for rq in all_rqs}
    dim_to_rqs: dict[str, list[dict]] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        q_ids = dp.get("question_ids") or []
        if dim_name and q_ids:
            dim_to_rqs[dim_name] = [rq_by_id[qid] for qid in q_ids if qid in rq_by_id]

    lines = ["## 研究背景"]
    if brief:
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")

    research_design_section = "\n".join(lines)

    dim_name = task_dim_map.get(str(task["task_id"]), "")
    task_lines = ["## 待判定任务"]
    task_lines.append(f"\n### 任务 #{task['task_id']}")
    task_lines.append(
        f"关键词: {task.get('keyword', '')} | 平台: {task.get('platform', '')}"
        + (f" | 维度: {dim_name}" if dim_name else "")
    )

    rqs_for_dim = dim_to_rqs.get(dim_name) if dim_name else None
    if rqs_for_dim:
        task_lines.append("本维度研究问题：")
        for rq in rqs_for_dim:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")
    elif all_rqs:
        task_lines.append("研究问题（参考全部，重点关注与本维度相关的）：")
        for rq in all_rqs:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")

    entity_match = task.get("entity_match", False)
    task_lines.append(f"entity_match: {entity_match}（{'品牌/竞品实体在内容中有出现' if entity_match else '品牌/竞品实体未在内容中出现'}）")
    task_lines.append(
        f"采集: {task.get('posts_count', 0)} 条"
        f"（深度分析 {task.get('deep_analyzed', 0)} 条）"
    )

    top_topics = task.get("top_topics") or []
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

    if task.get("promotion_ratio") is not None:
        task_lines.append(f"广告占比: {task['promotion_ratio']:.0%}（推广/软文帖子比例）")

    return {
        "research_design_section": research_design_section,
        "probe_tasks_section": "\n".join(task_lines),
    }


def parse_single_task_probe_review_response(response_text: str) -> dict[str, Any]:
    """解析单任务探测审查响应，返回单条 assessment dict，失败时抛出 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("Single Task Probe Review JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    if "verdict" not in result:
        raise ValueError(f"响应缺少 verdict 字段: {text[:200]}")

    return result

