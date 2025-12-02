#!/usr/bin/env python3
"""话题/Category 归一化 Chain

对聚合后的观点话题（category）进行同义词合并，减少冗余。
"""

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位话题归一化专家，负责对从社交媒体舆情数据中提取的观点话题进行同义词合并，减少冗余。

## 可以合并的情况
语义相同或高度相似的话题：
- 同义表述："价格"="定价"、"售后"="售后服务"
- 简称/完整表述："性能"="性能表现"、"外观"="外观设计"
- 近义话题："外观"="颜值"

## 不要合并的情况
- 相关但不同的话题："价格"和"性价比"、"物流"和"包装"

## 输出格式
```json
{{
  "normalized_groups": [
    {{
      "canonical_name": "代表性名称",
      "merged_categories": ["被合并的原始话题名称列表"]
    }}
  ],
  "standalone_categories": ["独立话题名称列表"]
}}
```

只输出JSON，不要有其他文字。
"""

CATEGORY_NORMALIZATION_USER_TEMPLATE = """请对以下话题列表进行归一化处理：

{categories}
"""


def create_category_normalization_chain() -> Runnable:
    """创建话题归一化的LangChain链

    Returns:
        Runnable: 用于话题归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE),
        ("user", CATEGORY_NORMALIZATION_USER_TEMPLATE),
    ])

    return prompt | llm


def format_categories_for_normalization(categories: list[dict[str, Any]]) -> str:
    """格式化话题列表用于归一化

    Args:
        categories: 话题列表，每个包含 name, score 字段

    Returns:
        str: 格式化后的话题列表字符串
    """
    return "\n".join([
        f"- {c['name']} (重要度: {c.get('score', 0):.1f})"
        for c in categories
    ])


def parse_category_normalization_response(response_text: str) -> dict[str, Any]:
    """解析LLM归一化响应

    Args:
        response_text: LLM返回的文本

    Returns:
        dict: 包含 normalized_groups, standalone_categories, category_mapping
    """
    # 清理可能的 markdown 代码块
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    result = json.loads(response_text.strip())

    # 构建话题映射表（原名称 -> 归一化名称）
    category_mapping = {}
    for group in result.get("normalized_groups", []):
        canonical_name = group.get("canonical_name", "")
        for merged in group.get("merged_categories", []):
            category_mapping[merged] = canonical_name

    for standalone in result.get("standalone_categories", []):
        category_mapping[standalone] = standalone

    result["category_mapping"] = category_mapping
    return result
