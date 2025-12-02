#!/usr/bin/env python3
"""实体归一化 Chain

对聚合后的实体进行同义词合并，减少冗余。
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


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
      "canonical_name": "代表性名称",
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


def create_entity_normalization_chain() -> Runnable:
    """创建实体归一化的LangChain链

    Returns:
        Runnable: 用于实体归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_NORMALIZATION_SYSTEM_TEMPLATE),
        ("user", ENTITY_NORMALIZATION_USER_TEMPLATE),
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
