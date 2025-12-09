#!/usr/bin/env python3
"""实体归一化/聚类 Chain

对聚合后的实体进行同义词合并，减少冗余。
支持两阶段归一化：初步归一化 + 复查修正。
引入多维标签 (Facet) 系统，支持 Role/Category/Parent 维度。
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


# ==================== 第一阶段：初步归一化与打标 ====================

ENTITY_CLUSTERING_SYSTEM_TEMPLATE = """你是一位语义分析专家，负责处理社交媒体实体数据。
当前分析的核心主题（锚点）是：【{task_keywords}】。

你的任务是：
1. **归一化**：合并指向同一事物的同义词实体，减少冗余。
2. **多维打标**：基于核心主题和提供的[线索]，为每个实体输出三个维度的标签。

## 标签定义体系 (Facet System)

### 1. role (与主题的关系)
回答"它是谁？"
- `Target` (我方/主体): 用户关注的核心分析对象（如本品牌、本品、子产品）。
- `Competitor` (竞品/对手): 与主体构成直接竞争关系的品牌或产品。
- `Context` (背景/中立): 提及的场景、行业大词、无关实体或通用词。

### 2. category (自然品类)
回答"它是什么东西？"
- 提取实体的物理属性或自然分类（如：手机、耳机、地点、人物、服务）。
- 请使用最简短的词。

### 3. parent (归属/上级)
回答"它归属在哪里？"
- 实体所属的品牌或上级系列。
- **动态逻辑**：
  - 如果实体是产品 -> 填品牌名（如"华为"）。
  - 如果实体是品牌 -> 填"Self"或所属集团。
  - 如果实体是通用词 -> 填所属大类（如"户外装备"）。

## 合并规则
- 指向同一事物的不同表述必须合并（如 "Mate60 Pro" 和 "华为Mate60"）。
- 不要合并不同型号或不同品牌的产品。

## 输出格式
```json
{{
  "entities": [
    {{
      "name": "标准名称（代表性名称）",
      "original_names": ["被合并的原始实体名称列表"],
      "role": "Target/Competitor/Context",
      "category": "品类词",
      "parent": "归属词"
    }}
  ]
}}
```
只输出JSON，不要有其他文字。
"""

ENTITY_CLUSTERING_USER_TEMPLATE = """请对以下实体列表进行处理：

{entities}
"""


# ==================== 第二阶段：复查与标签修正 ====================

ENTITY_REVIEW_SYSTEM_TEMPLATE = """你是一位实体归一化审核专家。
当前分析的核心主题（锚点）是：【{task_keywords}】。

你的任务是审核第一阶段的结果，重点检查**合并错误**和**标签一致性**。

## 审核清单

### 1. 检查合并 (Normalization Check)
- **遗漏合并**：有没有把同义词分开了？（如 "iPhone 15" 和 "苹果15"）
- **错误合并**：有没有把竞品合并到本品里了？（严禁把 Competitor 合并进 Target）

### 2. 检查标签 (Tag Refinement)
- **role 准确性**：
  - 显然的竞品是否被标记为了 `Competitor`？（参考[线索]中的对比信息）
  - 主题相关的实体是否被标记为了 `Target`？
- **category 一致性**：
  - 同一类东西，不要有的填"电话"，有的填"手机"，请统一术语。
- **parent 准确性**：
  - 品牌归属是否正确？

## 输出要求
- 输出修正后的完整结果。
- **必须**为所有实体保留标签字段。
- 输出格式必须与输入相同（JSON）。

```json
{{
  "entities": [
    {{
      "name": "标准名称",
      "original_names": ["原始名称1", "原始名称2"],
      "role": "Target/Competitor/Context",
      "category": "品类词",
      "parent": "归属词"
    }}
  ]
}}
```
只输出JSON，不要有其他文字。
"""

ENTITY_REVIEW_USER_TEMPLATE = """请审核以下处理结果：

## 原始实体列表（含线索）
{original_entities}

## 第一阶段结果
{first_pass_result}

请仔细检查并输出最终结果。
"""


def create_entity_clustering_chain() -> Runnable:
    """创建实体归一化/聚类的LangChain链（第一阶段）

    Returns:
        Runnable: 用于实体归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_CLUSTERING_SYSTEM_TEMPLATE),
        ("user", ENTITY_CLUSTERING_USER_TEMPLATE),
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


def format_entities_for_clustering(entities: list[dict[str, Any]]) -> str:
    """格式化实体列表用于归一化/聚类

    Args:
        entities: 实体列表，每个包含 name, type, score, hint 字段

    Returns:
        str: 格式化后的实体列表字符串
    """
    lines = []
    for e in entities:
        line = f"- {e['name']} (类型: {e.get('type', '其他')}, 重要度: {e.get('score', 0):.1f})"
        if e.get("hint"):
            line += f" [线索]: {e['hint']}"
        lines.append(line)
    return "\n".join(lines)


def parse_clustering_response(response_text: str) -> dict[str, Any]:
    """解析LLM归一化/聚类响应

    Args:
        response_text: LLM返回的文本

    Returns:
        dict: 包含 entities, entity_mapping, tags_mapping
    """
    # 清理可能的 markdown 代码块
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from LLM response: {response_text[:100]}...")
        return {"entities": [], "entity_mapping": {}, "tags_mapping": {}}

    # 构建实体映射表（原名称 -> 归一化名称）
    entity_mapping = {}
    # 构建标签映射表（归一化名称 -> tags）
    tags_mapping = {}

    for entity in result.get("entities", []):
        name = entity.get("name", "")
        if not name:
            continue
            
        # 构建 tags
        tags = {
            "role": entity.get("role", "Context"),
            "category": entity.get("category", ""),
            "parent": entity.get("parent", ""),
        }
        tags_mapping[name] = tags

        # 构建映射：每个 original_name -> name
        for original in entity.get("original_names", [name]):
            entity_mapping[original] = name

    result["entity_mapping"] = entity_mapping
    result["tags_mapping"] = tags_mapping
    return result


async def cluster_entities_with_review(
    entities: list[dict[str, Any]],
    task_keywords: list[str] | None = None,
    enable_review: bool = True
) -> dict[str, Any]:
    """执行两阶段实体归一化/聚类（异步版本）

    Args:
        entities: 实体列表
        task_keywords: 任务关键词列表（锚点）
        enable_review: 是否启用复查阶段，默认启用

    Returns:
        dict: 归一化结果，包含 entities, entity_mapping, tags_mapping
    """
    if not entities:
        return {
            "entities": [],
            "entity_mapping": {},
            "tags_mapping": {}
        }
    
    # 转换关键词为字符串
    keywords_str = ", ".join(task_keywords) if task_keywords else "未指定"

    formatted_entities = format_entities_for_clustering(entities)

    # 第一阶段：初步归一化
    logger.info(f"实体归一化第一阶段：处理 {len(entities)} 个实体")
    normalization_chain = create_entity_clustering_chain()
    first_response = await normalization_chain.ainvoke({
        "entities": formatted_entities,
        "task_keywords": keywords_str
    })
    first_result = parse_clustering_response(first_response.content)

    if not enable_review:
        logger.info("复查阶段已禁用，返回第一阶段结果")
        return first_result

    # 第二阶段：复查修正
    logger.info("实体归一化第二阶段：复查修正")
    review_chain = create_entity_review_chain()

    # 格式化第一阶段结果用于复查
    first_pass_json = json.dumps({
        "entities": first_result.get("entities", [])
    }, ensure_ascii=False, indent=2)

    review_response = await review_chain.ainvoke({
        "original_entities": formatted_entities,
        "first_pass_result": first_pass_json,
        "task_keywords": keywords_str
    })

    final_result = parse_clustering_response(review_response.content)
    logger.info(f"实体归一化完成：{len(final_result.get('entities', []))} 个实体")

    return final_result


def cluster_entities_with_review_sync(
    formatted_entities: str,
    invoke_with_stats_fn,
    task_keywords: list[str] | None = None,
    enable_review: bool = True,
    llm_type: str = "chat"
) -> tuple[dict[str, Any], dict[str, Any]]:
    """执行两阶段实体归一化/聚类（同步版本，支持 token 统计）

    设计用于 Celery 任务环境，使用调用方提供的 invoke_with_stats_fn 来追踪 token。

    Args:
        formatted_entities: 已格式化的实体列表字符串
        invoke_with_stats_fn: token 统计的调用函数
        task_keywords: 任务关键词列表（锚点）
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
    
    # 转换关键词为字符串
    keywords_str = ", ".join(task_keywords) if task_keywords else "未指定"

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
    normalization_chain = create_entity_clustering_chain()
    first_response, first_stats = invoke_with_stats_fn(
        normalization_chain,
        {
            "entities": formatted_entities,
            "task_keywords": keywords_str
        },
        llm_type
    )
    merge_stats(first_stats)

    first_response_text = first_response.content if hasattr(first_response, "content") else str(first_response)
    first_result = parse_clustering_response(first_response_text)

    if not enable_review:
        logger.info("复查阶段已禁用，返回第一阶段结果")
        return first_result, combined_stats

    # 第二阶段：复查修正
    logger.info("实体归一化第二阶段：复查修正")
    review_chain = create_entity_review_chain()

    # 格式化第一阶段结果用于复查
    first_pass_json = json.dumps({
        "entities": first_result.get("entities", [])
    }, ensure_ascii=False, indent=2)

    review_response, review_stats = invoke_with_stats_fn(
        review_chain,
        {
            "original_entities": formatted_entities,
            "first_pass_result": first_pass_json,
            "task_keywords": keywords_str
        },
        llm_type
    )
    merge_stats(review_stats)

    review_response_text = review_response.content if hasattr(review_response, "content") else str(review_response)
    final_result = parse_clustering_response(review_response_text)

    logger.info(f"[实体归一化] 两步归一化完成，输出 {len(final_result.get('entities', []))} 个实体")

    # 更新合并统计的平均值
    if combined_stats['summary']['total_calls'] > 0:
        combined_stats['summary']['avg_tokens_per_call'] = (
            combined_stats['summary']['total_tokens'] / combined_stats['summary']['total_calls']
        )
        combined_stats['summary']['avg_cost_per_call'] = (
            combined_stats['summary']['total_cost_cny'] / combined_stats['summary']['total_calls']
        )

    logger.info(f"实体归一化完成：{len(final_result.get('entities', []))} 个实体")

    return final_result, combined_stats
