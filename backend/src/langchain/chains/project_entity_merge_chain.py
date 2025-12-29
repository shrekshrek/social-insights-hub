#!/usr/bin/env python3
"""项目级实体合并/打标 Chain（Project Snapshot Entity Merge）

目标：在项目级快照场景下，对跨任务聚合后的 Top 实体进行再归一化，并输出稳定的 Role/Parent 标签。
采用 **两阶段模式 (Merge -> Review)** 以最大限度减少幻觉和跨品类错误。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


# ==================== 第一阶段：合并与打标 (Merge) ====================

PROJECT_ENTITY_MERGE_SYSTEM_TEMPLATE = """你是一位语义分析专家，负责处理社交媒体实体数据（项目级合并场景）。

## 输入说明
- 实体列表：每行包含实体名、类型、重要度与线索。
- subject（主体）：{subject}
- competitors（竞品列表）：{competitors}

## 你的任务
1) **归一化**：合并指向同一事物的同义词实体。
2) **打标**：输出 role (Target/Competitor/Context) 和 parent (品牌)。

## 关键规则（严格遵守）
1. **严禁跨品类合并**：即使品牌相同，也不要将不同品类的产品合并。
   - 错误示例：在分析“智能手机”时，将同品牌的“充电器”、“手机壳”或“耳机”合并进“手机”实体中。
   - 正确做法：它们应作为两个独立实体。
2. **Role 仲裁**：
   - 若 subject 非空，指向该品牌的实体必须为 `Target`。
   - competitors 列表中的品牌必须为 `Competitor`。
   - 若 subject 为空，所有 role 均为 `Context`。
3. **Parent 优先**：优先使用线索中的 `parent候选`。

## 输出格式（JSON Only）
```json
{{
  "entities": [
    {{
      "name": "标准名称",
      "original_names": ["原始名称1", "原始名称2"],
      "role": "Target/Competitor/Context",
      "parent": "品牌名"
    }}
  ]
}}
```
"""

PROJECT_ENTITY_MERGE_USER_TEMPLATE = """请处理以下实体：

{entities}
"""


# ==================== 第二阶段：审计与纠错 (Review) ====================

PROJECT_ENTITY_REVIEW_SYSTEM_TEMPLATE = """你是一位严厉的数据审计员。你的任务是审查并修正实体归一化的结果。

## 审计重点（必须修正以下错误）
1. **拆分跨品类错误**：
   - 检查每个分组的 `original_names`。
   - 如果发现 **明显不同品类/性质** 的实体混入（例如在“主产品”组中混入了“配件”、“周边”、“完全不相关的同名物品”），**必须**将它们从该组中剔除，恢复为独立实体。
   - 例子：若 [某品牌手机] 组包含了 "某品牌冰箱" 或 "某品牌数据线"，请将其移出。

2. **强制 Role 校验**：
   - Subject: 【{subject}】 -> 必须是 `Target`
   - Competitors: 【{competitors}】 -> 必须是 `Competitor`
   - 任何违反此规则的实体，强制修正 role。

3. **Parent 逻辑检查**：
   - 确保 Parent 字段不与 entity name 本身逻辑冲突（例如 entity 是 "BrandA"，Parent 不应是 "BrandB"）。
   - 确保同一分组内的实体 Parent 保持一致。

## 输入
- 第一阶段结果 (JSON)

## 输出
修正后的完整 JSON，格式不变。
"""

PROJECT_ENTITY_REVIEW_USER_TEMPLATE = """请审核并修正以下结果：

{first_pass_result}
"""


def create_project_entity_merge_chain() -> Runnable:
    """创建第一阶段合并链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PROJECT_ENTITY_MERGE_SYSTEM_TEMPLATE),
            ("user", PROJECT_ENTITY_MERGE_USER_TEMPLATE),
        ]
    )
    return prompt | llm


def create_project_entity_review_chain() -> Runnable:
    """创建第二阶段审计链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PROJECT_ENTITY_REVIEW_SYSTEM_TEMPLATE),
            ("user", PROJECT_ENTITY_REVIEW_USER_TEMPLATE),
        ]
    )
    return prompt | llm


def parse_project_entity_merge_response(response_text: str) -> Dict[str, Any]:
    """解析 JSON 响应"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
    except Exception:
        logger.error(f"JSON Parse Error: {response_text[:200]}...")
        return {"entities": [], "entity_mapping": {}, "tags_mapping": {}}

    if not isinstance(result, dict):
        return {"entities": [], "entity_mapping": {}, "tags_mapping": {}}

    # 重建 mapping
    entity_mapping: dict[str, str] = {}
    tags_mapping: dict[str, dict[str, Any]] = {}

    for entity in result.get("entities", []) or []:
        if not isinstance(entity, dict):
            continue
        name = (entity.get("name") or "").strip()
        if not name:
            continue
        tags_mapping[name] = {
            "role": entity.get("role", "Context"),
            "parent": entity.get("parent", "") or "",
        }
        originals = entity.get("original_names") or [name]
        if isinstance(originals, list):
            for original in originals:
                if isinstance(original, str) and original.strip():
                    entity_mapping[original.strip()] = name

    result["entity_mapping"] = entity_mapping
    result["tags_mapping"] = tags_mapping
    return result


async def merge_project_entities_with_review(
    entities_text: str, subject: str, competitors: str, enable_review: bool = True
) -> Dict[str, Any]:
    """
    执行两阶段项目实体合并：
    1. Merge: 初步归一化
    2. Review: 审计跨品类错误和规则违规
    """
    # 1. First Pass
    merge_chain = create_project_entity_merge_chain()
    first_res = await merge_chain.ainvoke(
        {"entities": entities_text, "subject": subject, "competitors": competitors}
    )

    first_json_str = (
        first_res.content if hasattr(first_res, "content") else str(first_res)
    )

    if not enable_review:
        return parse_project_entity_merge_response(first_json_str)

    # 2. Second Pass (Review)
    # 解析一次以确保格式正确，再转回 JSON 给 Reviewer
    temp_parsed = parse_project_entity_merge_response(first_json_str)
    if not temp_parsed.get("entities"):
        return temp_parsed

    clean_json_input = json.dumps(
        {"entities": temp_parsed["entities"]}, ensure_ascii=False, indent=2
    )

    review_chain = create_project_entity_review_chain()
    review_res = await review_chain.ainvoke(
        {
            "first_pass_result": clean_json_input,
            "subject": subject,
            "competitors": competitors,
        }
    )

    final_json_str = (
        review_res.content if hasattr(review_res, "content") else str(review_res)
    )
    return parse_project_entity_merge_response(final_json_str)


def merge_project_entities_with_review_sync(
    entities_text: str,
    subject: str,
    competitors: list[str],
    invoke_with_stats_fn,
    enable_review: bool = True,
    llm_type: str = "chat",
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    同步版本：执行两阶段项目实体合并，支持 stats 统计。
    """
    combined_stats = {
        "summary": {
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_cny": 0.0,
            "total_duration_seconds": 0.0,
        },
        "call_details": [],
    }

    def merge_stats(stats: dict[str, Any]):
        if not stats:
            return
        summary = stats.get("summary", {})
        combined_stats["summary"]["total_calls"] += summary.get("total_calls", 0)
        combined_stats["summary"]["total_input_tokens"] += summary.get(
            "total_input_tokens", 0
        )
        combined_stats["summary"]["total_output_tokens"] += summary.get(
            "total_output_tokens", 0
        )
        combined_stats["summary"]["total_tokens"] += summary.get("total_tokens", 0)
        combined_stats["summary"]["total_cost_cny"] += summary.get(
            "total_cost_cny", 0.0
        )
        combined_stats["summary"]["total_duration_seconds"] += summary.get(
            "total_duration_seconds", 0.0
        )
        combined_stats["call_details"].extend(stats.get("call_details", []))

    competitors_str = str(competitors)

    # 1. First Pass
    logger.info("[Project Merge] Phase 1: Initial Merge")
    merge_chain = create_project_entity_merge_chain()
    first_res, first_stats = invoke_with_stats_fn(
        merge_chain,
        {"entities": entities_text, "subject": subject, "competitors": competitors_str},
        llm_type,
    )
    merge_stats(first_stats)

    first_json_str = (
        first_res.content if hasattr(first_res, "content") else str(first_res)
    )
    first_result = parse_project_entity_merge_response(first_json_str)

    if not enable_review:
        return first_result, combined_stats

    # 2. Second Pass (Review)
    if not first_result.get("entities"):
        logger.warning(
            "[Project Merge] Phase 1 returned empty entities, skipping review."
        )
        return first_result, combined_stats

    logger.info("[Project Merge] Phase 2: Audit & Review")
    clean_json_input = json.dumps(
        {"entities": first_result["entities"]}, ensure_ascii=False, indent=2
    )

    review_chain = create_project_entity_review_chain()
    review_res, review_stats = invoke_with_stats_fn(
        review_chain,
        {
            "first_pass_result": clean_json_input,
            "subject": subject,
            "competitors": competitors_str,
        },
        llm_type,
    )
    merge_stats(review_stats)

    final_json_str = (
        review_res.content if hasattr(review_res, "content") else str(review_res)
    )
    final_result = parse_project_entity_merge_response(final_json_str)

    return final_result, combined_stats
