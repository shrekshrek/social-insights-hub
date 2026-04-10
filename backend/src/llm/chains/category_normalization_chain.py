#!/usr/bin/env python3
"""观点类别归一化 Chain

负责将松散的观点类别（如"单价"、"售价"、"费用"）归一化为标准类别（如"价格"）。
"""

import json
import logging
from typing import Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位数据治理专家。
你的任务是将输入的【通用观点类别列表】归一化为**标准分类体系**。

## 任务背景
这些类别来自社交媒体中"不针对特定实体的通用观点"。
不同用户可能使用不同词汇描述同一维度（如"单价"、"售价"、"费用"都指"价格"）。

## 标准分类参考（可根据输入动态调整）
- 产品（含：质量、功能、设计、外观、体验）
- 价格（含：售价、单价、费用、性价比、优惠）
- 服务（含：态度、售后、物流、客服）
- 行业（含：市场、趋势、竞争、政策）
- 营销（含：活动、广告、代言）
- 其他

## 任务要求
1. **合并同义词**：将含义相近的类别聚合到同一标准名称下。
2. **保持简洁**：标准名称 2-4 字。
3. **覆盖全量**：所有输入类别都必须归入某个聚类。

## 输出格式
```json
{{
  "clusters": [
    {{"name": "标准类别名", "original_terms": ["原始类别1", "原始类别2"]}}
  ]
}}
```
只输出JSON。
"""

CATEGORY_NORMALIZATION_USER_TEMPLATE = """请对以下观点类别进行归一化：

{categories}
"""


def create_category_normalization_chain() -> Runnable:
    """创建类别归一化的LangChain链"""
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE),
            ("user", CATEGORY_NORMALIZATION_USER_TEMPLATE),
        ]
    )

    return prompt | llm


def format_categories_for_normalization(category_counts: Dict[str, int]) -> str:
    """格式化类别列表用于归一化

    Args:
        category_counts: {类别名称: 频次}
    """
    sorted_items = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

    lines = []
    for cat, count in sorted_items:
        lines.append(f"- {cat} ({count})")

    return "\n".join(lines)


def parse_category_normalization_response(response_text: str) -> Dict[str, str]:
    """解析类别归一化响应，返回 {原始类别: 标准类别} 映射"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())

        # 从 clusters 格式转换为 mapping
        mapping = {}
        for cluster in result.get("clusters", []):
            name = cluster.get("name", "")
            for term in cluster.get("original_terms", []):
                mapping[term] = name
        return mapping

    except json.JSONDecodeError:
        logger.error(
            f"Failed to decode JSON from Category Normalization response: {response_text[:100]}..."
        )
        return {}
