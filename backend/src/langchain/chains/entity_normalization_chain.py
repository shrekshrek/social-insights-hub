#!/usr/bin/env python3
"""实体归一化 Chain

对聚合后的实体进行同义词合并，减少冗余。
支持两阶段归一化：初步归一化 + 复查修正。
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


# ==================== 第一阶段：初步归一化 ====================

ENTITY_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位实体归一化专家，负责对从社交媒体舆情数据中提取的实体进行同义词合并，减少冗余。

## 可以合并的情况
指向同一事物的不同表述：
- 简称/全称："小米"="小米科技"、"阿里"="阿里巴巴"
- 中英文名："苹果"="Apple"、"微软"="Microsoft"
- 拼写变体："华为"="HUAWEI"
- 同一事物不同叫法："iPhone"="苹果手机"
- 类型不同但同一事物："京东"(品牌)和"京东商城"(服务)可合并，选择其中更合适的类型

## 不要合并的情况
- 通用品类词 vs 具体品牌："手机"不能归并到"苹果"、"电脑"不能归并到"联想"
- 不同的事物："笔记本"和"台式机"、"检测"和"治理"

## 输出格式
```json
{{
  "normalized_groups": [
    {{
      "canonical_name": "代表性名称（选择最通用、最常见的名称）",
      "type": "实体类型",
      "merged_entities": ["被合并的原始实体名称列表"]
    }}
  ],
  "standalone_entities": ["独立实体名称列表"]
}}
```

只输出JSON，不要有其他文字。
"""

ENTITY_NORMALIZATION_USER_TEMPLATE = """请对以下实体列表进行归一化处理：

{entities}
"""


# ==================== 第二阶段：复查修正 ====================

ENTITY_REVIEW_SYSTEM_TEMPLATE = """你是一位实体归一化审核专家，负责审核归一化结果，检查并修正错误。

## 审核要点

### 1. 遗漏合并（应合并但未合并）
检查是否有语义相同但未被合并的实体：
- 简称/全称关系
- 中英文对应
- 同义词、别名
- 同一产品的不同叫法

### 2. 错误合并（不应合并但被合并）
检查是否有不同概念被错误地合并：
- 通用品类词不应归入具体品牌
- 相关但不同的概念（如"价格"和"性价比"）
- 不同产品线或不同公司的产品

### 3. 代表名选择
检查 canonical_name 是否选择了最通用、最常见、最能代表该组的名称

### 4. 类型准确性
检查实体类型是否正确分类

## 输出要求
- 如果发现问题，输出修正后的完整结果
- 如果没有问题，原样输出（不要修改）
- 输出格式必须与输入相同

只输出JSON，不要有其他文字。
"""

ENTITY_REVIEW_USER_TEMPLATE = """请审核以下实体归一化结果：

## 原始实体列表
{original_entities}

## 初步归一化结果
{first_pass_result}

请仔细检查是否有遗漏合并、错误合并、代表名选择不当或类型错误的问题，并输出最终结果。
"""


def create_entity_normalization_chain() -> Runnable:
    """创建实体归一化的LangChain链（第一阶段）

    Returns:
        Runnable: 用于实体归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_NORMALIZATION_SYSTEM_TEMPLATE),
        ("user", ENTITY_NORMALIZATION_USER_TEMPLATE),
    ])

    return prompt | llm


def create_entity_review_chain() -> Runnable:
    """创建实体归一化复查的LangChain链（第二阶段）

    Returns:
        Runnable: 用于复查归一化结果的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_REVIEW_SYSTEM_TEMPLATE),
        ("user", ENTITY_REVIEW_USER_TEMPLATE),
    ])

    return prompt | llm


def format_entities_for_normalization(entities: list[dict[str, Any]]) -> str:
    """格式化实体列表用于归一化

    Args:
        entities: 实体列表，每个包含 name, type, score 字段

    Returns:
        str: 格式化后的实体列表字符串
    """
    return "\n".join([
        f"- {e['name']} (类型: {e.get('type', '其他')}, 重要度: {e.get('score', 0):.1f})"
        for e in entities
    ])


def parse_normalization_response(response_text: str) -> dict[str, Any]:
    """解析LLM归一化响应

    Args:
        response_text: LLM返回的文本

    Returns:
        dict: 包含 normalized_groups, standalone_entities, entity_mapping
    """
    # 清理可能的 markdown 代码块
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    result = json.loads(response_text.strip())

    # 构建实体映射表（原名称 -> 归一化名称）
    entity_mapping = {}
    for group in result.get("normalized_groups", []):
        canonical_name = group.get("canonical_name", "")
        for merged in group.get("merged_entities", []):
            entity_mapping[merged] = canonical_name

    for standalone in result.get("standalone_entities", []):
        entity_mapping[standalone] = standalone

    result["entity_mapping"] = entity_mapping
    return result


async def normalize_entities_with_review(
    entities: list[dict[str, Any]],
    enable_review: bool = True
) -> dict[str, Any]:
    """执行两阶段实体归一化（异步版本）

    Args:
        entities: 实体列表
        enable_review: 是否启用复查阶段，默认启用

    Returns:
        dict: 归一化结果
    """
    if not entities:
        return {
            "normalized_groups": [],
            "standalone_entities": [],
            "entity_mapping": {}
        }

    formatted_entities = format_entities_for_normalization(entities)

    # 第一阶段：初步归一化
    logger.info(f"实体归一化第一阶段：处理 {len(entities)} 个实体")
    normalization_chain = create_entity_normalization_chain()
    first_response = await normalization_chain.ainvoke({"entities": formatted_entities})
    first_result = parse_normalization_response(first_response.content)

    if not enable_review:
        logger.info("复查阶段已禁用，返回第一阶段结果")
        return first_result

    # 第二阶段：复查修正
    logger.info("实体归一化第二阶段：复查修正")
    review_chain = create_entity_review_chain()

    # 格式化第一阶段结果用于复查
    first_pass_json = json.dumps({
        "normalized_groups": first_result.get("normalized_groups", []),
        "standalone_entities": first_result.get("standalone_entities", [])
    }, ensure_ascii=False, indent=2)

    review_response = await review_chain.ainvoke({
        "original_entities": formatted_entities,
        "first_pass_result": first_pass_json
    })

    final_result = parse_normalization_response(review_response.content)
    logger.info(f"实体归一化完成：{len(final_result.get('normalized_groups', []))} 个合并组，"
                f"{len(final_result.get('standalone_entities', []))} 个独立实体")

    return final_result


def normalize_entities_with_review_sync(
    formatted_entities: str,
    invoke_with_stats_fn,
    enable_review: bool = True,
    llm_type: str = "chat"
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行两阶段实体归一化（同步版本，支持 token 统计）

    设计用于 Celery 任务环境，使用调用方提供的 invoke_with_stats_fn 来追踪 token。

    Args:
        formatted_entities: 已格式化的实体列表字符串
        invoke_with_stats_fn: token 统计的调用函数，签名为 (chain, input_dict, llm_type) -> (response, stats)
        enable_review: 是否启用复查阶段，默认启用
        llm_type: LLM 类型

    Returns:
        tuple: (归一化结果, 合并的 token 统计)
    """
    combined_stats = {
        'summary': {
            'total_calls': 0,
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_tokens': 0,
            'total_cost_cny': 0.0,
            'total_duration_seconds': 0.0,
        },
        'call_details': [],
    }

    def merge_stats(stats: dict[str, Any]):
        """合并 token 统计"""
        if not stats:
            return
        summary = stats.get('summary', {})
        combined_stats['summary']['total_calls'] += summary.get('total_calls', 0)
        combined_stats['summary']['total_input_tokens'] += summary.get('total_input_tokens', 0)
        combined_stats['summary']['total_output_tokens'] += summary.get('total_output_tokens', 0)
        combined_stats['summary']['total_tokens'] += summary.get('total_tokens', 0)
        combined_stats['summary']['total_cost_cny'] += summary.get('total_cost_cny', 0.0)
        combined_stats['summary']['total_duration_seconds'] += summary.get('total_duration_seconds', 0.0)
        combined_stats['call_details'].extend(stats.get('call_details', []))

    # 第一阶段：初步归一化
    logger.info("实体归一化第一阶段：初步归一化")
    normalization_chain = create_entity_normalization_chain()
    first_response, first_stats = invoke_with_stats_fn(
        normalization_chain,
        {"entities": formatted_entities},
        llm_type
    )
    merge_stats(first_stats)

    first_response_text = first_response.content if hasattr(first_response, "content") else str(first_response)
    first_result = parse_normalization_response(first_response_text)

    if not enable_review:
        logger.info("复查阶段已禁用，返回第一阶段结果")
        return first_result, combined_stats

    # 第二阶段：复查修正
    logger.info("实体归一化第二阶段：复查修正")
    review_chain = create_entity_review_chain()

    # 格式化第一阶段结果用于复查
    first_pass_json = json.dumps({
        "normalized_groups": first_result.get("normalized_groups", []),
        "standalone_entities": first_result.get("standalone_entities", [])
    }, ensure_ascii=False, indent=2)

    review_response, review_stats = invoke_with_stats_fn(
        review_chain,
        {
            "original_entities": formatted_entities,
            "first_pass_result": first_pass_json
        },
        llm_type
    )
    merge_stats(review_stats)

    review_response_text = review_response.content if hasattr(review_response, "content") else str(review_response)
    final_result = parse_normalization_response(review_response_text)

    # 更新合并统计的平均值
    if combined_stats['summary']['total_calls'] > 0:
        combined_stats['summary']['avg_tokens_per_call'] = (
            combined_stats['summary']['total_tokens'] / combined_stats['summary']['total_calls']
        )
        combined_stats['summary']['avg_cost_per_call'] = (
            combined_stats['summary']['total_cost_cny'] / combined_stats['summary']['total_calls']
        )

    logger.info(f"实体归一化完成：{len(final_result.get('normalized_groups', []))} 个合并组，"
                f"{len(final_result.get('standalone_entities', []))} 个独立实体")

    return final_result, combined_stats
