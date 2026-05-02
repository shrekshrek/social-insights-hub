"""Strategy Coverage Check Chain — 数据覆盖度验证

基于切片量化指标对照研究问题评估覆盖度。三态判定 + 渠道相对量级指引，
输出 per-RQ status / overall_ready / warnings / data_highlights / slice_adjustments。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SYSTEM_TEMPLATE = """你是一位数据覆盖度评估专家，负责判断已采集数据是否足以支撑下游产出生成。

## 任务
对每个研究问题判定其在切片中的覆盖度，并给出整体就绪判定与跨问题警示。

## 字段说明

切片摘要中每个实体 / 话题带量化指标：
- `mentions`：被提及的总次数（含同源帖多次）
- `sources`：独立源帖数（**关键信号**——同样 mentions 下，sources 越多代表信号越分散可靠，sources=1 代表单帖伪相关）
- `sentiment`：综合情感（-1 ~ +1）

## 判定逻辑（per 研究问题）

逐个研究问题，识别切片中能支撑该 RQ 的相关实体 / 话题（不限于 RQ 字面词，语义相关即可），然后判定其覆盖状态：

**covered（充分支撑）**：
- 至少一个相关实体 / 话题被 **≥3 个独立源帖** 讨论
  - 社媒切片：source ≥3 个帖子
  - 新闻切片：source ≥3 篇独立文章
- 数字 3 是统计学上"互相佐证"的最低线（避免单帖偏见 / 双帖巧合）

**partial（部分支撑）**：
- 有相关实体 / 话题命中，但 source 仅 1-2（信号偏单薄）
- 或多个相关项但分布零散（每项都仅 1 源帖支撑）
- 全量阶段可能补强但当前 evidence 不充分

**uncovered（无支撑）**：
- 切片中完全无相关实体 / 话题命中
- 或仅有 mention=1 / source=1 的极端单点提及（噪音级别）

## overall_ready 规则

- **true**：所有 `priority=high` 的 RQ 状态 ∈ {covered, partial}
- **false**：任一 `priority=high` 的 RQ 状态 = uncovered
- medium / low priority RQ 不影响 overall_ready，仅影响 warnings

## warnings 字段（关键）

当存在以下情况时，输出 warning（每条单句，明确指出受影响 RQ）：
- 多个 RQ 共同因为同一个 slice 数据稀疏而 partial / uncovered（例："slice X 数据稀疏，影响 rq1/rq2"）
- subject 在某 slice 完全缺失但该 slice 是该 RQ 的唯一数据源
- partial RQ 的具体补强建议（如"补采小红书任务可能改善 rq3"）

无 warning 时返回空数组。

## 输出格式

只输出 JSON，不要 markdown 标记：

{{
  "question_coverage": [
    {{
      "question_id": "rq1",
      "question": "研究问题原文",
      "status": "covered",
      "covered_by": ["切片名称1"],
      "evidence_summary": "美赞臣在 social_slice_1 提及 85 次跨 42 源帖，consumer voice 充分"
    }}
  ],
  "overall_ready": true,
  "warnings": ["slice X 整体数据稀疏，影响 rq2/rq3——建议补采小红书任务"],
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

- question_coverage 必须覆盖所有研究问题，status 三态之一
- evidence_summary **必须包含量化数字**（mentions / sources），让审查者可追溯
- data_highlights：2-4 条对策略生成有价值的数据发现
- slice_adjustments：仅当切片配置确有问题时输出，否则空数组
- warnings 优先承载跨 RQ 共性诊断，不要把每个 partial RQ 都当 warning
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


def _format_entity_line(e: dict, *, source_key: str) -> str:
    """渲染单个实体/话题行，统一格式：name(role): mentions=N, sources=M, sentiment=..."""
    name = e.get("name", "")
    role = e.get("role", "") or e.get("category", "")
    mentions = e.get("mentions") or e.get("mention_count") or 0
    sources = e.get(source_key) or 0
    sentiment = e.get("sentiment") or e.get("sentiment_avg")
    parts = [f"mentions={mentions}", f"sources={sources}"]
    if sentiment is not None:
        try:
            parts.append(f"sentiment={float(sentiment):+.2f}")
        except (TypeError, ValueError):
            pass
    role_str = f"({role})" if role else ""
    return f"  - {name}{role_str}: {', '.join(parts)}"


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
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
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
        is_news = name.startswith("[新闻]")

        if is_news:
            # 新闻切片 result_data 结构（ADR-003 后）：
            #   descriptive: sentiment_distribution / sentiment_overall / articles_unique / articles_filtered
            #   entities: [{name, role, mention_count, source_count, sentiment_avg, ...}]
            #   event_clusters / media_landscape / competitive: 派生层
            #   page_synthesis: Pass 2 LLM 散文（briefing + event_titles），策略层禁用
            descriptive = data.get("descriptive") or {}
            entities = data.get("entities") or []
            dist = descriptive.get("sentiment_distribution") or {}
            total_articles = sum(dist.get(k, 0) for k in ("positive", "neutral", "negative"))
            slice_lines.append(f"渠道: 新闻 | 原文数: {total_articles}")
            overall_sent = descriptive.get("sentiment_overall")
            if overall_sent is not None:
                label = "正面" if overall_sent > 0.6 else "负面" if overall_sent < 0.4 else "中性"
                slice_lines.append(f"整体情感: {label}（{overall_sent:.2f}）")
            if entities:
                slice_lines.append(f"主要实体（前 {min(15, len(entities))} 个）:")
                for e in entities[:15]:
                    if e.get("name"):
                        slice_lines.append(_format_entity_line(e, source_key="source_count"))
        else:
            # 社媒切片 result_data 结构: {meta, foundation, layers, reports, pipeline}
            foundation = data.get("foundation") or {}
            landscape = (data.get("layers") or {}).get("landscape") or {}
            overview = landscape.get("overview") or {}
            total_volume = overview.get("total_volume", 0) or overview.get("unique_posts", 0)
            slice_lines.append(f"渠道: 社媒 | 总声量: {total_volume}")

            global_nsr = overview.get("global_nsr")
            if global_nsr is not None:
                label = "正面" if global_nsr > 0.3 else "负面" if global_nsr < -0.3 else "中性"
                slice_lines.append(f"整体情感: {label}（NSR={global_nsr:.2f}）")

            entities = (foundation.get("aligned_entities") or [])[:15]
            if entities:
                slice_lines.append(f"主要实体（前 {len(entities)} 个）:")
                for e in entities:
                    if e.get("name"):
                        slice_lines.append(_format_entity_line(e, source_key="source_count"))

            topics = (foundation.get("aligned_topics") or [])[:10]
            if topics:
                slice_lines.append(f"主要话题（前 {len(topics)} 个）:")
                for t in topics:
                    if t.get("name"):
                        slice_lines.append(_format_entity_line(t, source_key="source_count"))

    slices_summary_section = "\n".join(slice_lines)

    return {
        "brief_section": brief_section,
        "research_questions_section": research_questions_section,
        "slices_summary_section": slices_summary_section,
    }


def parse_coverage_check_response(response_text: str) -> dict[str, Any]:
    """解析覆盖度验证 Chain 输出，失败时抛出 ValueError。

    Schema: question_coverage[].status (covered/partial/uncovered) + warnings 字段。
    """
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
    result.setdefault("warnings", [])
    result.setdefault("data_highlights", [])
    result.setdefault("slice_adjustments", [])

    return result
