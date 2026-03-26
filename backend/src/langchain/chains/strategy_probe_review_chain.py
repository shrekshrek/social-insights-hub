"""Strategy Probe Review Chain — 探测数据质量审查

基于探测采集（≈20 条）的分析结果，评估每个关键词×平台任务的话题相关性：
- 客观规则（代码层）：数量、广告占比 → 明确 pass/fail（由调用方处理）
- 语义判断（LLM 层）：话题是否对应研究维度的研究问题（模糊案例）
- 优化建议（LLM 层）：为 fail 任务推荐更合适的关键词，或建议新增未覆盖的任务

输出每个任务的 pass/fail 判定、判定依据、关键词建议，以及可选的新增任务建议。
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

**独立原则**：每个任务基于自身话题数据单独评估，结论不受同批次其他任务影响。相同的话题数据应得到相同的判定。

每个任务已标注维度，请只对照该维度下的研究问题进行判断，不要参考其他维度的研究问题。

- **pass**：话题与该维度研究问题的核心关注点有明显关联
- **fail**：话题与该维度研究问题明显无关（收集到的内容完全答不上研究问题）

**保守偏置**：存疑时判 pass——全量采集后分析结果会暴露真正的问题，误判 fail 会浪费关键词调整机会。

## 关键词建议（仅 fail 时填写）

好的替换关键词应满足：在该平台搜索时，能召回与研究问题核心关注点直接相关的内容。
结合「已采集到的话题（知道现在收到了什么）」与「研究问题（知道需要什么）」之间的差距来推导建议词。
**suggested_keyword 是提交给平台的单一搜索查询**（可包含空格，如"某品牌 用户评价"），禁止用 `|` 拼接多个备选查询——给出你认为最优的那一个即可。
如果 fail 的原因是「该平台本身不适合此类研究」或「同维度已有其他任务能覆盖」，可将 suggested_keyword 设为 null，表示建议直接移除该任务而非替换。

各平台替换词格式参考：
- 知乎：加"怎么样/如何评价"等评价词能精准命中问题标题，纯品牌名召回较泛
- 微博：品牌名 + 口碑类词（口碑/评价/怎么样）效果好；纯品牌名噪音大
- 小红书：加"测评/体验/推荐/避坑"类词能精准召回消费者评价
- 抖音/B站：简短品牌名 + 场景词/评测词效果好

## 新增任务建议（可选）

在完成所有任务评估后，如果你在探测数据中发现了**明确有价值、且当前任务集完全未覆盖**的话题角度，可以建议新增采集任务。

**严格标准，满足以下全部��件才建议新增：**
1. 该话题在多个现有任务中反复出现，说明平台用户真实关注
2. 现有任务集中没有任何任务在采集这个角度的内容
3. 该话题与某个研究问题直接相关，补充后能实质性提升研究质量

**不应新增的情况：**
- 话题只在个别任务中偶尔提及
- 现有任务调整关键词后就能覆盖（优先替换，而非新增）
- 纯粹是感觉"可能有用"，没有明确的话题证据

新增建议保持克制，通常 0-2 条，不要为了完整性而堆砌建议。

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
  ],
  "add_suggestions": [
    {{
      "keyword": "建议新增的搜索查询",
      "platform": "平台代码",
      "dimension": "所属维度名称（必须与 data_plan 中的 dimension_name 完全一致）",
      "reason": "一句话说明：在哪些任务的话题中发现了什么信号 → 为何值得新增"
    }}
  ]
}}

**规则：**
- 每个任务均需给出 assessment
- verdict 只能是 pass 或 fail
- verdict=fail 时：suggested_keyword 给出替换关键词，suggestion_reason 说明「当前收到了什么 vs 需要什么 → 为何推荐这个词」；pass 时均为 null
- add_suggestions 无新增建议时输出空数组 `[]`，不要省略该字段
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
    brief: dict | None = None,
) -> dict[str, Any]:
    """格式化探测审查链输入

    Args:
        research_design: 研究计划 JSON
        tasks: 需要 LLM 判定 verdict 的任务（已通过客观规则预筛选，排除明确 pass/fail）
        brief: 品牌 Brief，用于锚定评估方向
    """
    task_dim_map = research_design.get("_task_dimension_map") or {}
    data_plan = research_design.get("data_plan", [])
    all_rqs = research_design.get("research_questions", [])

    # 构建 dimension_name → 研究问题列表 的映射（通过 data_plan.question_ids 显式链接）
    rq_by_id = {rq.get("id"): rq for rq in all_rqs}
    dim_to_rqs: dict[str, list[dict]] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        q_ids = dp.get("question_ids") or []
        if dim_name and q_ids:
            dim_to_rqs[dim_name] = [rq_by_id[qid] for qid in q_ids if qid in rq_by_id]

    # 研究背景
    lines = ["## 研究背景"]

    if brief:
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")

    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")

    # 数据维度名称列表，add_suggestions.dimension 必须从此列表中取值
    if data_plan:
        lines.append("\n### 数据维度（add_suggestions 的 dimension 字段必须与此完��一致）")
        for dp in data_plan:
            dim_name = dp.get("dimension_name", "")
            if dim_name:
                lines.append(f"- {dim_name}")

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

        # 内联显示该维度对应的研究问题，避免 LLM 跨节跳转推断维度映射
        rqs_for_dim = dim_to_rqs.get(dim_name) if dim_name else None
        if rqs_for_dim:
            task_lines.append(f"本维度研究问题：")
            for rq in rqs_for_dim:
                task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")
        elif all_rqs:
            # 无显式映射时，展示全部研究问题供参考
            task_lines.append(f"研究问题（参考全部，重点关注与本维度相关的）：")
            for rq in all_rqs:
                task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")
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
    result.setdefault("add_suggestions", [])
    return result
