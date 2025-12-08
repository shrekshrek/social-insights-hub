#!/usr/bin/env python3
"""观点类别归一化 Chain

负责将松散的观点类别（如"单价"、"售价"、"费用"）归一化为标准类别（如"价格"）。
"""

import json
import logging
from typing import Any, Dict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位数据治理专家。
你的任务是将输入的【观点类别列表】归一化为**标准分类体系**。

## 任务背景
在舆情分析中，不同来源可能会使用不同的词汇描述同一个维度（如"单价"、"售价"都指"价格"）。
我们需要消除这些同义词，减少维度碎片化。

## 标准分类建议（仅供参考，可根据输入动态调整）
- 价格 (含：售价、单价、费用、性价比)
- 产品 (含：质量、功能、设计、外观)
- 服务 (含：态度、售后、物流、配送)
- 营销 (含：活动、广告、代言人)
- 品牌 (含：企业形象、公关)
- 行业 (含：市场趋势、竞品)
- 用户 (含：人群、粉丝)
- 其他

## 任务要求
1. **合并同义词**：将含义相近的类别映射到同一个标准名称。
2. **保持简洁**：标准名称最好是2-4个字的通用名词。
3. **覆盖全量**：输入列表中的所有类别都必须有对应的映射（如果是标准词则映射到自身）。

## 输入格式
类别列表，格式为：
- 类别名称 (频次)

## 输出格式
```json
{{
  "mapping": {{
    "原始类别1": "标准类别A",
    "原始类别2": "标准类别A",
    "原始类别3": "标准类别B"
  }}
}}
```
只输出JSON，不要有其他文字。
"""

CATEGORY_NORMALIZATION_USER_TEMPLATE = """请对以下观点类别进行归一化：

{categories}
"""


def create_category_normalization_chain() -> Runnable:
    """创建类别归一化的LangChain链"""
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", CATEGORY_NORMALIZATION_SYSTEM_TEMPLATE),
        ("user", CATEGORY_NORMALIZATION_USER_TEMPLATE),
    ])

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
    """解析类别归一化响应"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
        return result.get("mapping", {})
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from Category Normalization response: {response_text[:100]}...")
        return {}

