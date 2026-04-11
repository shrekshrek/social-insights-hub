#!/usr/bin/env python3
"""属性归一化 Chain

对实体的属性列表（features, issues, expectations）进行语义聚类和标准化。
将松散的短语合并为标准化的描述。
"""

import json
import logging
from typing import Any, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)


ATTRIBUTE_NORMALIZATION_SYSTEM_TEMPLATE = """你是一位数据清洗与归纳专家。
你的任务是对输入的产品评价短语列表进行**语义聚类**和**标准化**。

## 任务要求
1. **合并同义词**：将语义相同或高度相关的短语合并（如 "发热"、"烫手"、"温度高" -> "发热严重"）。
2. **提取标准名**：为每个聚类生成一个简练、专业、具有描述性的标准短语（Label）。
3. **保持原意**：标准短语必须忠实反映原始短语的含义，不要过度推断。
4. **覆盖率**：输入列表中的所有短语都应该被归入某个聚类中（除非完全无意义）。

## 输入格式
输入为一个短语列表，每个短语后面带有频次信息，如：
- 发热 (10)
- 拍照好看 (5)

## 输出格式
```json
{{
  "clusters": [
    {{"name": "标准短语", "original_terms": ["原始短语1", "原始短语2"]}}
  ]
}}
```
只输出JSON。
"""

ATTRIBUTE_NORMALIZATION_USER_TEMPLATE = """请对以下评价短语进行清洗和聚类：

{attributes}
"""


def create_attribute_normalization_chain() -> Runnable:
    """创建属性归一化的LangChain链

    Returns:
        Runnable: 用于属性归一化的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ATTRIBUTE_NORMALIZATION_SYSTEM_TEMPLATE),
            ("user", ATTRIBUTE_NORMALIZATION_USER_TEMPLATE),
        ]
    )

    return prompt | llm


def format_attributes_for_normalization(attributes_map: dict[str, set]) -> str:
    """格式化属性列表用于归一化

    Args:
        attributes_map: {原始短语: post_ids_set}

    Returns:
        str: 格式化后的属性列表字符串
    """
    # 按频次降序排列
    sorted_items = sorted(attributes_map.items(), key=lambda x: len(x[1]), reverse=True)

    lines = []
    for term, post_ids in sorted_items:
        lines.append(f"- {term} ({len(post_ids)})")

    return "\n".join(lines)


def parse_normalization_response(response_text: str) -> List[dict[str, Any]]:
    """解析归一化响应

    Args:
        response_text: LLM返回的文本

    Returns:
        List[dict]: 归一化后的聚类列表 [{"label": str, "original_terms": list}]
    """
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(response_text.strip())
        return result.get("clusters", [])
    except json.JSONDecodeError:
        logger.error(
            f"Failed to decode JSON from Attribute Normalization response: {response_text[:100]}..."
        )
        return []
