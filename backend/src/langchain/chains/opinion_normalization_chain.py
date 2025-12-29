#!/usr/bin/env python3
"""观点归一化 Chain

对通用观点（General Opinions）进行语义聚类和标准化。
将松散的用户表达（如"太贵了"、"买不起"）归纳为标准的观点陈述（如"定价过高"）。
"""

import json
import logging
from typing import Any, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm

logger = logging.getLogger(__name__)


OPINION_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位资深的舆情分析师。
你的任务是对同一类别下的【用户观点列表】进行**语义归纳**和**标准化**。

## 任务要求
1. **语义聚类**：将表达相同含义的观点合并（如"太贵了"、"买不起" -> "定价过高"）。
2. **提取标准名 (Label)**：为每个聚类生成一个简练、客观、准确的**陈述句**或**短语**，必须忠实反映原始情感倾向。
3. **全面覆盖**：输入列表中的所有有效观点都应被归入某个聚类。
4. **去噪**：丢弃完全无意义的语气词或无关内容。

## 输入说明
输入是一组用户在社交媒体上的真实评论片段（已按类别分组），格式为：
- 观点内容 (频次)

## 输出格式
```json
{{
  "clusters": [
    {{"name": "标准观点", "original_terms": ["原始观点1", "原始观点2"]}}
  ]
}}
```
只输出JSON。
"""

OPINION_NORMALIZATION_USER_TEMPLATE = """请对以下【{category}】类别的用户观点进行归纳和标准化：

{opinions}
"""


def create_opinion_normalization_chain() -> Runnable:
    """创建观点归一化的LangChain链"""
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", OPINION_NORMALIZATION_SYSTEM_TEMPLATE),
            ("user", OPINION_NORMALIZATION_USER_TEMPLATE),
        ]
    )

    return prompt | llm


def format_opinions_for_normalization(opinions_map: dict[str, Any]) -> str:
    """格式化观点列表用于归一化

    Args:
        opinions_map: {原始观点: post_ids_set 或 频次}
                      可以是 dict[str, set] 或 dict[str, int]
    """
    # 统一获取频次
    items = []
    for term, value in opinions_map.items():
        count = (
            len(value) if isinstance(value, set) or isinstance(value, list) else value
        )
        items.append((term, count))

    # 按频次降序排列
    sorted_items = sorted(items, key=lambda x: x[1], reverse=True)

    lines = []
    for term, count in sorted_items:
        lines.append(f"- {term} ({count})")

    return "\n".join(lines)


def parse_normalization_response(response_text: str) -> List[dict[str, Any]]:
    """解析归一化响应"""
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
        return result.get("clusters", [])
    except json.JSONDecodeError:
        logger.error(
            f"Failed to decode JSON from Opinion Normalization response: {response_text[:100]}..."
        )
        return []
